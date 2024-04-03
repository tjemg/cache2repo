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

headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:99.0) Gecko/20100101 Firefox/99.0"
          }

def fetchURL( url ):
    try:
        response = requests.get(url, headers=headers)
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
                        allWantedPkg[line] = 1
        return allWantedPkg
    except Exception as e:
        return None

def getNewDeps( currList, allPkg ):
    newDeps = {}
    try:
        for p in currList:
            dp = allPkg[p].get("deps",{})
            for dpn in dp:
                if dpn not in currList:
                    #print(f"New dependency: {dpn}")
                    newDeps[dpn] = 1
        return newDeps
    except Exception as e:
        print(f"ERROR: unknown package {p}")
        sys.exit(0)

def main():
    global g_verboseMode 
    global g_meta
    repoURL = "https://pkg.FreeBSD.org/FreeBSD:14:aarch64/quarterly"

    try:
        opts, args = getopt.getopt(sys.argv[1:], "u:h")
    except getopt.GetoptError as err:
        usage()
        sys.exit(2)
    for o, a in opts:
        if o in ("-u"):
            repoURL = a
        else:
            assert False, "unhandled option"
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
    print("Downloading packages...")
    for p in pkgToDownload:
        fileURL = repoURL+"/"+allPkg[p]["repopath"]
        fileName = "repo/" + p + "-" + allPkg[p]["version"] + ".pkg"
        fileContents = fetchURL(fileURL)
        with open(fileName,"wb") as f:
            f.write(fileContents)
        print(f"{fileURL} -> {fileName}" )

if __name__ == "__main__":
    main()
