* FreeBSD cache2repo

This small script will create an ISO image out of your current FreeBSD pkg cache

Run the script simply:

./cache2repo

A new file called *mirror.iso* will be created. You can copy/burn the image.
On the target system, can do the following:

  1) Mount the ISO, e.g.
        mkdir /mirror
        mdconfig -a -t vnode -f mirror.iso -u 0
        mount -t cd9660 /dev/md0 /mirror

  2) [optional] Bootstrap pkg
        cd /
        tar xvzf mirror/pkg-bootstrap.tgz

  3) Install packages, e.g.
        pkg install mc vim

  4) Cleanup mirror
        umount /mirror
        mdconfig -d -u 0
        rmdir /mirror

That's all :-)
