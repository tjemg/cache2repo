#!/usr/local/bin/python3.9
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
#    mount -t cd9660 /dev/md0 /mirror
#
#    umount /mirror
#    mdconfig -d -u 0
#
import requests
import tarfile
import getopt
import json
import glob
import sys
import re
import os
import io

g_headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:99.0) Gecko/20100101 Firefox/99.0"
          }

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

def fetchURL( url ):
    global g_headers
    try:
        response = requests.get(url, headers=g_headers)
        if response.status_code == 200:
            return response.content
        else:
            return None
    except Exception as e:
        return None

def extractFromTXZ( inData, wantedFile):
    try:
        with tarfile.open(fileobj=io.BytesIO(inData), mode='r:xz') as tar:
            file_data = tar.extractfile(wantedFile)
            if file_data:
                return file_data.read()
            else:
                print(f"File '{wantedFile}' not found in the archive.")
                return None
    except tarfile.TarError as e:
        print("Error extracting file:", e)
        return None

def loadPackageListFromURL( url ):
    pkgList = {}
    pSite = fetchURL(url)
    if pSite != None:
        pSiteYAML = extractFromTXZ(pSite, "packagesite.yaml")
        if pSiteYAML:
            for p in pSiteYAML.decode().split("\n"):
                try:
                    if p == "": continue
                    package = json.loads(p)
                    pName = package["name"]
                    pkgList[pName] = package
                except:
                    return None
        else:
            return None
    else:
        return None
    return pkgList

def loadWantedPkg( fileName ):
    allWantedPkg = {}
    try:
        with open(fileName, "r") as f:
            lines = f.read().split("\n")
            for line in lines:
                if line != "":
                    if line[0]!="#":
                        allWantedPkg[line] = line
        return allWantedPkg
    except Exception as e:
        return None

def getNewDeps( currList, allPkg ):
    newDeps = {}
    willQuit = False
    for p in currList:
        # print(f"Searching for dependencies of {p}")
        try:
            thisPkg = None
            try:
                thisPkg = allPkg[p]
            except Exception as e:
                print("ERROR:",e)
                willQuit = True
            if thisPkg is not None:
                dp = thisPkg.get("deps",{})
                for dpn in dp:
                    if dpn not in currList:
                        #print(f"New dependency: {dpn}")
                        newDeps[dpn] = 1
        except Exception as e:
            print(f"ERROR: unknown package {p} - " + str(e))
            willQuit = True
    if willQuit:
        exit(0)
    return newDeps

def help():
    print("")
    print("repo2repo: create a local mirror of a FreeBSD repository")
    print("")
    print("  -u <URL>      : example http://pkg.freebsd.org/FreeBSD:14:amd64/latest/")
    print("  -r <path>     : local path to store the repository [default = repo]")
    print("  -v <version>  : FreeBSD version [default = 14]")
    print("  -c <cpu>      : CPU type, e.g. amd64, aarch64 [default = amd64]")
    print("  -e <endpoint> : repository endpoint, e.g. latest, release_2 [default = quarterly]]")
    print("  -i <file.iso> : output ISO file [default = None]]")
    print("  -k            : keep repo path")
    print("")

def main():
    global g_verboseMode 
    global g_meta
    global g_mirror
    cpuType = "amd64"
    version = "14"
    endpoint = "quarterly"
    localRepoPath = "repo"
    forceRepoURL = None
    isoFile = None
    keepRepoPath = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], "u:hr:v:c:e:i:k")
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-u"):
            forceRepoURL = a
        elif o in ("-r"):
            localRepoPath = a
        elif o in ("-v"):
            version = a
        elif o in ("-c"):
            cpuType = a
        elif o in ("-e"):
            endpoint = a
        elif o in ("-i"):
            isoFile = a
        elif o in ("-k"):
            keepRepoPath = True
        elif o in ("-h"):
            help()
            exit(0)
        else:
            assert False, "unhandled option: "+str(o)

    if os.path.exists(localRepoPath):
        if not os.path.isdir(localRepoPath):
            print(f"ERROR: destination path ({localRepoPath}) is not a directory!")
            exit(0)

    if not os.path.exists(localRepoPath):
        os.system(f"mkdir {localRepoPath}")

    if os.path.exists(localRepoPath):
        if not os.path.isdir(localRepoPath):
            print(f"ERROR: unknown error in repo path creation!")
            exit(0)
    else:
        print(f"ERROR: could not create destination path ({localRepoPath})")
        exit(0)

    if forceRepoURL is None:
        repoURL = f"https://pkg.FreeBSD.org/FreeBSD:{version}:{cpuType}/{endpoint}"
    else:
        repoURL = forceRepoURL
    url = repoURL+"/packagesite.txz"
    print(f"Getting list of packages from: {url}")
    allPkg = loadPackageListFromURL(url)
    print(f"Getting list of wanted packages from: selected.txt")
    wp = loadWantedPkg("selected.txt")
    pkgToDownload = dict(wp)
    print("Generating list of packages to fetch...")
    while True:
        np = getNewDeps(pkgToDownload, allPkg)
        if np != {}:
            for p in np: pkgToDownload[p] = 1
        else:
            break
    localPaths = []
    print("Downloading packages...")
    for p in pkgToDownload:
        repoPath = allPkg[p]["repopath"]
        fileURL = repoURL+"/" + repoPath
        fileName = localRepoPath + "/" + repoPath
        localPath = os.path.dirname(os.path.realpath(fileName))
        if localPath not in localPaths:
            localPaths.append(localPath)
            os.system(f"mkdir {localPath}")
        fileContents = fetchURL(fileURL)
        with open(fileName,"wb") as f:
            f.write(fileContents)
        print(f"{fileURL} -> {fileName}" )
        with open(localRepoPath+"/packagesite.yaml","a") as f:
            f.write(json.dumps(allPkg[p]))
            f.write("\n")
    print("Generating meta.conf...")
    with open(localRepoPath+"/"+"meta.conf","w") as f:
        f.write(g_meta)
    print("Generating packagesite.txz...")
    os.system(f"cd {localRepoPath}; bsdtar -cvof packagesite.txz packagesite.yaml > /dev/null 2> /dev/null")
    print("Generating packagesite.pkg...")
    os.system(f"cd {localRepoPath}; cp packagesite.txz packagesite.pkg")

    print("Preparing pkg for bootstraping...")
    os.system(f"mkdir -p {localRepoPath}/usr/sbin/; cp /usr/sbin/pkg {localRepoPath}/usr/sbin/pkg")
    os.system(f"mkdir -p {localRepoPath}/usr/local/sbin/; cp /usr/local/sbin/pkg {localRepoPath}/usr/local/sbin/pkg; cp /usr/local/sbin/pkg-static {localRepoPath}/usr/local/sbin/pkg-static")
    os.system(f"mkdir -p {localRepoPath}/usr/local/etc/; cp /usr/local/etc/pkg.conf {localRepoPath}/usr/local/etc/pkg.conf")
    os.system(f"mkdir -p {localRepoPath}/etc/pkg/")
    with open(localRepoPath+"/etc/pkg/"+"mirror.conf","w") as f:
        f.write(g_mirror)
    os.system(f"cd {localRepoPath}; tar cvzf pkg-bootstrap.tgz etc usr; rm -rf etc usr")

    if not isoFile is None:
        os.system(f"mkisofs -R -o mirror.iso {localRepoPath}")
        if not keepRepoPath:
            os.system(f"rm -rf {localRepoPath}")

if __name__ == "__main__":
    main()
