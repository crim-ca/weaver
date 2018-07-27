if [ -f /etc/debian_version ] ; then
    echo "Installing Debian/Ubuntu packages ..."
    sudo apt-get -y update
elif [ -f /etc/redhat-release ] ; then
    echo "Installing RedHat/CentOS packages ..."
    sudo yum -y update
elif [ `uname -s` = "Darwin" ] ; then
    echo "Installing MacOSX/Homebrew packages ..."
    #brew install wget
fi
