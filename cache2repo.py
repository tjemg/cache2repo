#!/usr/local/bin/python
#
# (C) 2024, Tiago Gasiba
#           tiago.gasiba@gmail.com
#
#  pkg install py39-sqlite
#  pkg install cdrtools
#
#
# To mount the ISO:
#    mdconfig -a -t vnode -f ISO -u 0
#    mount -t udf /dev/md0 /mirror
#
#    umount /mirror
#    mdconfig -d -u 0
#
import subprocess
import sqlite3
import hashlib
import getopt
import json
import glob
import sys
import re
import os

g_licenses = {}
g_categories = {}
g_shlibs = {}
g_option = {}
g_annotation = {}
g_groups = {}
g_users = {}
g_licenselogic = {}
g_deps = {}
g_verboseMode = False
g_meta = """version = 2;
packing_format = "txz";
manifests = "packagesite.yaml";
filesite = "filesite.yaml";
manifests_archive = "packagesite";
filesite_archive = "filesite";
"""
g_mirror = """FreeBSD_mirror: {
  url: "file:///mirror/",
  mirror_type: "srv",
  signature_type: "none",
  enabled: yes
}
"""

RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
WHITE  = "\033[1;37m"
GREEN  = "\033[0;32m"
BLUE   = "\033[0;34m"
RESET  = "\033[0m"

def fileExists( fName ):
    try:
        fd = open(fName,"r")
        fd.close()
        return True
    except:
        return False

def getLicenses( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_licenses WHERE package_id={packageID}")
    retLicenses = []
    for l in x:
        retLicenses.append(g_licenses.get(l[1],"unknown"))
    return retLicenses

def getCategories( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_categories WHERE package_id={packageID}")
    retCategories = []
    for c in x:
        retCategories.append(g_categories.get(c[1],"unknown"))
    return retCategories

def getRequiredSHLibs( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_shlibs_required WHERE package_id={packageID}")
    retShLibs= []
    for s in x:
        retShLibs.append(g_shlibs.get(s[1],"unknown"))
    return retShLibs

def getProvidedSHLibs( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_shlibs_provided WHERE package_id={packageID}")
    retShLibs= []
    for s in x:
        retShLibs.append(g_shlibs.get(s[1],"unknown"))
    return retShLibs

def getPackageOptions( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_option WHERE package_id={packageID}")
    retOptions = {}
    for o in x:
        optionID  = o[1]
        optionCfg = o[2]
        retOptions[ g_option[optionID] ] = optionCfg
    return retOptions

def getPackageAnnotations( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_annotation WHERE package_id={packageID}")
    retAnnotation = {}
    for a in x:
        a1 = a[1]
        a2 = a[2]
        retAnnotation[ g_annotation[a1] ] = g_annotation[a2]
    return retAnnotation

def getLicenseLogic( logic_id ):
    if logic_id in g_licenselogic:
        return g_licenselogic[logic_id]
    else:
        print(f"ERROR: unknown license logic - ID={logic_id}")
        sys.exit(0)

def getPackageGroups( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_groups WHERE package_id={packageID}")
    retGroups= []
    for g in x:
        retGroups.append(g_groups.get(g[1],"unknown"))
    return retGroups

def getPackageUsers( cursor, packageID ):
    x = cursor.execute(f"SELECT * FROM pkg_users WHERE package_id={packageID}")
    retUsers= []
    for g in x:
        retUsers.append(g_users.get(g[1],"unknown"))
    return retUsers

def computeCheckSum( localFileName ):
    checkSum = "unknown"
    with open(localFileName, "rb") as f:
        checkSum = hashlib.sha256()
        for chunk in iter(lambda: f.read(4096), b""):
            checkSum.update(chunk)
        checkSum = checkSum.hexdigest()
    return checkSum

def loadGlobalVars( cu ):
    global g_licenses
    global g_categories
    global g_shlibs
    global g_option
    global g_annotation
    global g_groups
    global g_users
    global g_licenselogic
    global RED
    global YELLOW
    global WHITE
    global GREEN
    global BLUE
    global RESET
    try:
        x = cu.execute("SELECT * FROM licenses")
        for l in x:
            g_licenses[l[0]] = l[1]
        
        x = cu.execute("SELECT * FROM categories")
        for c in x:
            g_categories[c[0]] = c[1]
        
        x = cu.execute("SELECT * FROM shlibs")
        for s in x:
            g_shlibs[s[0]] = s[1]
        
        x = cu.execute("SELECT * FROM option")
        for o in x:
            g_option[o[0]] = o[1]
        
        x = cu.execute("SELECT * FROM annotation")
        for a in x:
            g_annotation[a[0]] = a[1]
        
        x = cu.execute("SELECT * FROM groups")
        for o in x:
            g_groups[o[0]] = o[1]
        
        x = cu.execute("SELECT * FROM users")
        for o in x:
            g_users[o[0]] = o[1]
        
        g_licenselogic = {   1: "single",
                            38: "and",
                           124: "or"
                         }
    except Exception as e:
        print(f"{RED}ERROR{RESET}:",str(e))
        sys.exit(0)

def computeDeps(cu):
    global RED
    global YELLOW
    global WHITE
    global GREEN
    global BLUE
    global RESET
    try:
        print(f"{WHITE}Computing package dependencies...{RESET}")
        global g_deps
        g_deps = {}
        x = cu.execute("SELECT origin, name, version, package_id FROM deps")
        for p in x:
            origin, name, version, package_id = p
            if package_id not in g_deps:
                g_deps[package_id] = { name: {"origin":origin, "version":version} }
            else:
                g_deps[package_id][name] = {"origin":origin, "version":version}
    except Exception as e:
        print(f"{RED}ERROR{RESET}:",str(e))
        sys.exit(0)

def loadPackages(cu, localCache="/var/cache/pkg"):
    global g_verboseMode
    global RED
    global YELLOW
    global WHITE
    global GREEN
    global BLUE
    global RESET
    try:
        # Read all packages from local database
        x = cu.execute("SELECT id, name, origin, version, comment, maintainer, www, arch, prefix, flatsize, licenselogic, desc, message FROM packages")
        allPackages = []
        for n in x:
            package_id, name, origin, version, comment, maintainer, www, arch, prefix, flatsize, licenselogic, desc, message = n
            package = {}
            package["package_id"] = package_id
            package["name"] = name
            package["origin"] = origin
            package["version"] = version
            package["comment"] = comment
            package["maintainer"] = maintainer
            package["www"] = www
            package["arch"] = arch
            package["prefix"] = prefix
            package["flatsize"] = flatsize
            package["licenselogic"] = licenselogic
            package["desc"] = desc
            package["message"] = message
            allPackages.append(package)
        
        # Build a list of packages, based on local database + local cache
        print(f"{WHITE}Building list of local packages...{RESET}")
        repoPackages = []
        for p in allPackages:
            try:
                #if p["name"] != "binutils": continue
                fileName = p["name"] + "-" + p["version"] + ".pkg"
                localFileName = localCache + "/" + fileName
                #print(f"Adding {localFileName}")
                localFileSize = os.path.getsize(localFileName)
                localFileChecksum = computeCheckSum(localFileName)
                pkgLicences = getLicenses(cu,p["package_id"])
                pkgLicenseLogic = getLicenseLogic( p["licenselogic"] )
                pkgProvidedSHLibs = getProvidedSHLibs(cu,p["package_id"])
                pkgRequiredSHLibs = getRequiredSHLibs(cu,p["package_id"])
                pkgOptions = getPackageOptions(cu,p["package_id"])
                pkgGroups = getPackageGroups(cu,p["package_id"])
                pkgUsers = getPackageUsers(cu,p["package_id"])
                pkgLicenses = getLicenses(cu,p["package_id"])
                abi = p["arch"]
                arch = p["arch"].lower()
                if arch[-2:] != ":*" :
                    arch = arch + ":" + arch[-2:]
                pkgDesc = {  "name"              : p["name"],
                             "origin"            : p["origin"],
                             "version"           : p["version"],
                             "comment"           : p["comment"],
                             "maintainer"        : p["maintainer"],
                             "www"               : p["www"],
                             "abi"               : abi,
                             "arch"              : arch,
                             "prefix"            : p["prefix"],
                             "sum"               : localFileChecksum,
                             "flatsize"          : p["flatsize"],
                             "path"              : f"All/{fileName}",
                             "repopath"          : f"All/{fileName}",
                             "licenselogic"      : pkgLicenseLogic,
                             "pkgsize"           : localFileSize,
                             "desc"              : p["desc"],
                             "categories"        : getCategories(cu,p["package_id"]),
                             "annotations"       : getPackageAnnotations(cu,p["package_id"]),
                          }
                if [] != pkgProvidedSHLibs:
                    pkgDesc["shlibs_provided"] = pkgProvidedSHLibs
                if [] != pkgRequiredSHLibs:
                    pkgDesc["shlibs_required"] = pkgRequiredSHLibs
                if {} != pkgOptions:
                    pkgDesc["options"] = pkgOptions
                if p["package_id"] in g_deps:
                    pkgDesc["deps"] = g_deps[p["package_id"]]
                if (p["message"] != "") and (p["message"] != None):
                    pkgDesc["messages"] = p["message"]
                if pkgGroups != []:
                    pkgDesc["groups"] = pkgGroups
                if pkgUsers != []:
                    pkgDesc["users"] = pkgUsers
                if pkgLicences != []:
                    pkgDesc["licenses"] = pkgLicences
                repoPackages.append(pkgDesc)
            except Exception as e:
                if g_verboseMode: print(f"{RED}Exception{RESET}: "+str(e))
                next
    except Exception as e:
        print(f"{RED}ERROR{RESET}:",str(e))
        sys.exit(0)
    return repoPackages

def openLocalDB(localDBFile):
    global RED
    global YELLOW
    global WHITE
    global GREEN
    global BLUE
    global RESET
    try:
        cx = sqlite3.connect(localDBFile)
        cu = cx.cursor()
    except:
        print(f"{RED}ERROR{RESET}: could not open local DB file {localDBFile}")
        exit(0)
    return (cx,cu)

def usage():
    global RED
    global YELLOW
    global WHITE
    global GREEN
    global BLUE
    global RESET
    print("")
    print("cache2repo: create a mirror of a local FreeBSD pkg cache")
    print("")
    print("  -o <dir>       : output directory")
    print("  -i <ISOfile>   : ISO file name (default=mirror.iso)")
    print("  -V <volume_ID> : volume ID for the ISO file")
    print("  -n             : no color")
    print("")
    exit(0)

def main():
    global g_verboseMode 
    global g_meta
    global RED
    global YELLOW
    global WHITE
    global GREEN
    global BLUE
    global RESET

    outputDir   = "mirror"
    localDBFile = "/var/db/pkg/local.sqlite"
    cacheFolder = "/var/cache/pkg"
    g_verboseMode = False
    useColor = True
    isoFile = None
    volumeID = "FreeBSD"
    setVolID = None
    keepRepoPath = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "ho:vi:nV:k", ["help", "output="])
    except getopt.GetoptError as err:
        print(err)
        usage()
        exit(2)
    for o, a in opts:
        if   o in ("-v"): g_verboseMode = True
        elif o in ("-V"): setVolID = a
        elif o in ("-i"): isoFile = a
        elif o in ("-n"): useColor = False
        elif o in ("-k"): keepRepoPath = True
        elif o in ("-h", "--help"): usage()
        elif o in ("-o", "--output"): outputDir = a
        else:
            assert False, "unhandled option"

    if useColor == False:
        RED    = ""
        YELLOW = ""
        WHITE  = ""
        GREEN  = ""
        BLUE   = ""
        RESET  = ""

    if os.path.exists(outputDir):
        if not os.path.isdir(outputDir):
            print(f"{RED}ERROR{RESET}: destination path ({outputDir}) is not a directory!")
            exit(0)
    if not os.path.exists(outputDir):
        os.system(f"mkdir {outputDir}")

    cpuType = subprocess.check_output(["uname","-m"]).decode().strip("\n")

    if not setVolID is None:
        volumeID = setVolID
    else:
        volumeID = volumeID + "_" + cpuType

    conn, cursor = openLocalDB(localDBFile)
    loadGlobalVars(cursor)
    computeDeps(cursor)
    repoPackages = loadPackages(cursor)

    print(f"{WHITE}Generating packagesite.yaml...{RESET}")
    with open(outputDir+"/"+"packagesite.yaml","w") as f:
        for p in repoPackages:
            f.write(json.dumps(p)+"\n")

    print(f"{WHITE}Generating meta.conf...{RESET}")
    with open(outputDir+"/"+"meta.conf","w") as f:
        f.write(g_meta)

    print(f"{WHITE}Generating packagesite.txz...{RESET}")
    os.system(f"cd {outputDir}; bsdtar -cvof packagesite.txz packagesite.yaml > /dev/null 2> /dev/null")

    print(f"{WHITE}Generating packagesite.pkg...{RESET}")
    os.system(f"cd {outputDir}; cp packagesite.txz packagesite.pkg")

    print(f"{WHITE}Copying PKG files...{RESET}")
    os.system(f"mkdir -p {outputDir}/All; cd {outputDir}/All")
    for f in glob.glob(f"{cacheFolder}/*.pkg"):
        if not re.match(r".*~[0-9a-zA-Z]+.pkg$",f):
            fName = os.path.basename(f)
            print(f"{BLUE}{f}{RESET} -> {YELLOW}{outputDir}/All/{fName}{RESET}", flush=True )
            os.system(f"cp {f} {outputDir}/All")

    print(f"{WHITE}Preparing pkg for bootstraping...{RESET}")
    os.system(f"mkdir -p {outputDir}/usr/sbin/; cp /usr/sbin/pkg {outputDir}/usr/sbin/pkg")
    os.system(f"mkdir -p {outputDir}/usr/local/sbin/; cp /usr/local/sbin/pkg {outputDir}/usr/local/sbin/pkg; cp /usr/local/sbin/pkg-static {outputDir}/usr/local/sbin/pkg-static")
    os.system(f"mkdir -p {outputDir}/usr/local/etc/; cp /usr/local/etc/pkg.conf {outputDir}/usr/local/etc/pkg.conf")
    os.system(f"mkdir -p {outputDir}/etc/pkg/")

    with open(outputDir+"/etc/pkg/"+"mirror.conf","w") as f:
        f.write(g_mirror)

    os.system(f"cd {outputDir}; tar cvzf pkg-bootstrap.tgz etc usr; rm -rf etc usr")

    if not isoFile is None:
        print(f"{WHITE}Generating ISO file{RESET}: {isoFile}")
        os.system(f"mkisofs -R -V {volumeID} -UDF -o {isoFile} {outputDir}")
        if not keepRepoPath:
            print(f"{WHITE}Deleting {outputDir}{RESET}")
            os.system(f"rm -rf {outputDir}")

    # cleanup
    os.system(f"rm -f packagesite.yaml")
    os.system(f"rm -f packagesite.txz")
    os.system(f"rm -f meta.conf")

    conn.close()

    print(f"{GREEN}Done.{RESET}")

if __name__ == "__main__":
    main()
