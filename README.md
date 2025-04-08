# mini-savi
mininet combined with savi for satellite network simulation
# install
for ubuntu 18.04 / 22.04

1. sudo apt-get install git python3 pip3
2. sudo pip3 install mininet
3. sudo apt-get install geomview
4. sudo apt-get install mininet
5. sudo apt-get install tk-dev
6. git clone https://github.com/zhutang/mini-savi.git
7. cd mini-savi; sudo make ARCH=linux

# run
1. cd mini-savi/mini-savi; sudo python3 router-host.py
2. in another terminal, input: cd mini-savi; geomview -run ./savi
3. select constellation, for example iridium, and click run
