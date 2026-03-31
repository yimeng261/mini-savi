

#!/usr/bin/python

from mininet.net import Mininet
from mininet.node import Node
from mininet.link import Link
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.topo import Topo
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
import time
import socketserver
import os
import math
import subprocess
import threading

sat_lines = {}
sat_coor_lines = {}
sat_line_str = ''
sat_coor_line_str = ''
sats_str = {}  # 创建字典
sats_coor_str = {}  # 创建字典
net = None
ISLs = {}
ISLs_origin = {}
hosts = {}
sats = {}
TOPOLOGY = {
    "num_sats": 0,
    "sats_per_plane": 0,
    "num_planes": 0,
}


class Myserver(socketserver.StreamRequestHandler):
    sat_line_str = ''
    sat_coor_line_str = ''
    num = 0
    ISL_delays = {} #星间链路延时，为0表示不可见

    def _parse_satellite_tokens(self, line):
        tokens = [token for token in line.split(' ') if token]
        if not tokens:
            return None
        if tokens[-1] == 'sunlight':
            return None
        return tokens

    def _update_topology(self):
        global TOPOLOGY

        if self.num <= 0:
            TOPOLOGY["num_sats"] = 0
            TOPOLOGY["sats_per_plane"] = 0
            TOPOLOGY["num_planes"] = 0
            return

        last_sat = sats_str.get(self.num - 1, {})
        if len(last_sat) < 10:
            TOPOLOGY["num_sats"] = self.num
            TOPOLOGY["sats_per_plane"] = 1
            TOPOLOGY["num_planes"] = self.num
            return

        sats_per_plane = int(last_sat[9][0:-1]) + 1
        num_planes = int(self.num / sats_per_plane) if sats_per_plane else 0
        TOPOLOGY["num_sats"] = self.num
        TOPOLOGY["sats_per_plane"] = sats_per_plane
        TOPOLOGY["num_planes"] = num_planes

    def calc_sat_num(self):
        global net
        sats_str.clear()

        print("calc sat num")
        print(self.sat_line_str)
        k = 0
        i = 0
        j = 0
        sat_lines = self.sat_line_str.split('\r\n')
        print("sat_lines:", sat_lines)

        for line in sat_lines:  # 按行遍历
            #print("line:",line)
            if(line == 'constellation import end' or line == ''):
                print("found constellation import end")
                continue

            tokens = self._parse_satellite_tokens(line)
            if tokens is None:
                print("exclude sunlight")
                continue
            
            sats_str[i] = {}
            j = 0
            for arr in tokens:
                sats_str[i][j] = arr
                j = j + 1
            i = i + 1
        print("---------------------sats_str-----------------")
        print(sats_str)
        self.num = i  # 总卫星数目
        self._update_topology()
        print(i)
        
        myNet(self.num)

    def modify_ISL_para(self):
        global ISLs
        global ISLs_origin
        global TOPOLOGY

        #print("enter modify_ISL_para()")
        #print("self.num")
        #print(self.num)
        #print("---------------print self.ISL_delays---------------------")
        #print(self.ISL_delays)
        #print("---------------print ISLs---------------------")
        #print(ISLs)
        self.num = TOPOLOGY["num_sats"]
        sats_per_plane = TOPOLOGY["sats_per_plane"]
        if self.num <= 0 or sats_per_plane <= 0:
            return

        for i in range(0, self.num):
             for j in range(0, self.num):
                #print("i=%d, j=%d" % (i, j))
                islx = ISLs[i]
                islx_origin = ISLs_origin[i]
                if ((j in islx_origin.keys()) == False) :
                    continue
                
                if(i + sats_per_plane == j) or (i - sats_per_plane == j):
                    isl = ISLs[i][j]
                    #print(self.ISL_delays)
                    if(self.ISL_delays[i][j] != 0):
                        #ISLs[i][j] = None
                        sats[i].cmd('ifconfig ' + 'eth-r'+str(i+1)+'r'+str(j+1) + ' up')
                        sats[j].cmd('ifconfig ' + 'eth-r'+str(j+1)+'r'+str(i+1) + ' up')
                        print("up&&&&&&&%d%d"%(i,j))
                    else:
                        #ISLs[i][j] = None
                        sats[i].cmd('ifconfig ' + 'eth-r'+str(i+1)+'r'+str(j+1) + ' down')
                        sats[j].cmd('ifconfig ' + 'eth-r'+str(j+1)+'r'+str(i+1) + ' down')
                        print("down******%d%d"%(i,j))
    def calc_ISL_delay(self):
        print("enter calc_ISL_delay()")
        c = 300000
        r = 6371.0
        self.ISL_delays = {}
        sats_per_plane = TOPOLOGY["sats_per_plane"]
        sat_entries = []

        for key in sats_coor_str:
            sat_entry = sats_coor_str[key]
            sat_entries.append({
                "id": int(sat_entry[0]),
                "x": float(sat_entry[1]),
                "y": float(sat_entry[2]),
                "z": float(sat_entry[3]),
            })

        sat_entries.sort(key=lambda sat: sat["id"])

        for sat in sat_entries:
            sat["lat"] = get_latitude(sat["x"], sat["y"], sat["z"])
            self.ISL_delays[sat["id"] - 1] = {}

        for sat_a in sat_entries:
            id_a = sat_a["id"] - 1
            for sat_b in sat_entries:
                self.ISL_delays[id_a][sat_b["id"] - 1] = 0

        for idx_a, sat_a in enumerate(sat_entries):
            id_a = sat_a["id"] - 1
            x_a = sat_a["x"]
            y_a = sat_a["y"]
            z_a = sat_a["z"]
            lat_a = sat_a["lat"]

            for idx_b in range(idx_a + 1, len(sat_entries)):
                sat_b = sat_entries[idx_b]
                id_b = sat_b["id"] - 1
                x_b = sat_b["x"]
                y_b = sat_b["y"]
                z_b = sat_b["z"]
                lat_b = sat_b["lat"]
                delay = 0

                if sats_per_plane > 0 and (
                    lat_a > 60 or lat_a < -60 or lat_b > 60 or lat_b < -60
                ) and ((id_a // sats_per_plane) != (id_b // sats_per_plane)):
                    self.ISL_delays[id_a][id_b] = 0
                    self.ISL_delays[id_b][id_a] = 0
                    continue

                delta_x = x_a - x_b
                delta_y = y_a - y_b
                delta_z = z_a - z_b
                delta_sq = delta_x ** 2 + delta_y ** 2 + delta_z ** 2
                if delta_sq == 0:
                    continue

                t = (x_a * delta_x + y_a * delta_y + z_a * delta_z) / delta_sq
                dis_ab = math.sqrt(delta_sq)
                if t < 0 or t > 1:
                    delay = dis_ab / c
                else:
                    x_min = x_a + t * (x_b - x_a)
                    y_min = y_a + t * (y_b - y_a)
                    z_min = z_a + t * (z_b - z_a)

                    dis_min_abo = math.sqrt(x_min ** 2 + y_min ** 2 + z_min ** 2)
                    if r < dis_min_abo:
                        delay = dis_ab / c

                self.ISL_delays[id_a][id_b] = delay
                self.ISL_delays[id_b][id_a] = delay


        #print("---------------print self.ISL_delays---------------------")
        #print(self.ISL_delays)

    def parse_ISL_info(self):
        print("enter parse_ISL_info()")
        sats_coor_str.clear()
        #print(self.sat_coor_line_str)
        i = 0
        j = 0
        k = 0
        sat_coor_lines = self.sat_coor_line_str.split('\r\n')
        self.sat_coor_line_str = ''
        #print("sat_coor_lines:", sat_coor_lines)

        for line in sat_coor_lines:  # 按行遍历
            #print("line:",line)
            if(line == 'ISL info start' or line == 'ISL info end' or line == ''):
                #print("found - ", line)
                continue

            arrs = [arr for arr in line.split(', ') if arr != '']
            if len(arrs) < 5:
                continue

            if(arrs[4] == 'sunlight'): #exclude sunlight
                #print("exclude sunlight")
                continue
            
            sats_coor_str[i] = {}
            j = 0
            for arr in arrs:
                sats_coor_str[i][j] = arr
                j = j + 1
            i = i + 1
        #print("--------------------------sats_coor_str---------------------")
        #print(sats_coor_str)

        self.calc_ISL_delay()
        self.modify_ISL_para()

    def handle(self):
        start_import_flag = 0
        start_calc_links_flag = 0
        for raw_line in self.rfile:
            try:
                content = raw_line.decode('utf-8').strip()
                if not content:
                    continue

                if (content == 'constellation import start'):
                    start_import_flag = 1
                    print("start import routers")
                    self.sat_line_str = ''
                elif (content == 'constellation import end'):
                    print("calc sat num")
                    start_import_flag = 0
                    self.calc_sat_num()
                elif (content == 'forwards'):
                    print('net start\n')
                    #inet.start()
                elif (content == 'stop'):
                    print('net stop\n')
                    #net.stop()
                elif (content == 'ISL info start'):
                    print('recv ISL info start\n')
                    start_calc_links_flag = 1
                    self.sat_coor_line_str = ''
                elif (content == 'ISL info end'):
                    print('recv ISL info end\n')
                    start_calc_links_flag = 0
                    self.parse_ISL_info()
                else :  
                    if (start_import_flag == 1):
                        self.sat_line_str = self.sat_line_str + content + '\r\n'
                    if (start_calc_links_flag == 1):
                        self.sat_coor_line_str = self.sat_coor_line_str + content + '\r\n'
            except (ConnectionResetError, UnicodeDecodeError):
                break

def get_latitude(x, y, z):
    # 计算该点向量的模长
    r = math.sqrt(x ** 2 + y ** 2 + z ** 2)

    # 计算点的赤道面投影距离d
    d = math.sqrt(x ** 2 + y ** 2)

    # 计算点的纬度lat
    lat = math.atan2(z, d)

    # 将纬度转换为角度
    lat = lat * 180 / math.pi
    return lat


def myNet(num):

    "Create network from scratch using Open vSwitch."

    global ISLs
    global ISLs_origin
    global net
    global TOPOLOGY
    ISLs.clear()
    ISLs_origin.clear()
    sats.clear()

    if(net != None) :
        net.stop()
        #deleteIntfs??
        '''
        cs = net.controllers
        for c in cs  :
            net.delController(c)
        '''
        hs = net.hosts
        for h in hs  :
            net.delHost(h)
        sws = net.switches
        for s in  sws :
            net.delSwitch(s)
        '''
        ls = net.links
        for l in  ls :
            net.delLink(l)
        '''
    #os.system("mn -c")
    info('--cx----000---------------------------\n')
    info("*** Creating nodes\n")
    print(num)
    if (len(sats_str[num-1]) < 9): #example satellite
        M = 1
        N = 1
        print('construct example satellite')
        return
    else :
        #print(sats_str[num-1][9][0:-1])
        M = int(sats_str[num-1][9][0:-1]) + 1
        N = int(num / M)

    TOPOLOGY["num_sats"] = num
    TOPOLOGY["sats_per_plane"] = M
    TOPOLOGY["num_planes"] = N

    print("num is %d, N is %d, M is %d" % (num, N, M))
    #num = 33 # just for test
    #N = 3
    #M = 11
    for n in range(0, num):
        #h = net.addHost('h'+str(n+1), ip='192.168.123.' + str(n+100) + '/24')
        #h  = net.addHost(str(n)+'_host', ip='', cls=LinuxRouter)
        s = net.addHost('r'+str(n+1), ip='', cls=LinuxRouter)

        if (s == None) :
            print("switch add error")
            continue

        #net.addLink(h,s,intfName1='eth-h'+str(n)+'r'+str(n), intfName2='eth-r'+str(n)+'h'+str(n))
        #hosts[n] = h
        sats[n] = s

    for n in range(0, N): 
        for m in range(0, M):
            ISLs [n * M + m] = {}
            ISLs_origin [n * M + m] = {}

    for n in range(0, N):
        for m in range(0, M):
            isl1 = net.addLink(sats[n * M + m], sats[n * M + (m + 1) % M],intfName1='eth-r'+str(n * M + m+1)+'r'+str(n * M + (m + 1) % M+1), intfName2='eth-r'+str(n * M + (m + 1) % M+1)+'r'+str(n * M + m+1), bw=10, delay='1ms') #intra-satellite links
            ISLs [n * M + m][n * M + (m + 1) % M] = isl1
            ISLs_origin [n * M + m][n * M + (m + 1) % M] = isl1     #每个星链之间形成环路
            if (n != N - 1) :  # N-1说明没有跨缝的ISL
                isl2 = net.addLink(sats[n * M + m], sats[(n + 1) * M + m],intfName1='eth-r'+str(n * M + m+1)+'r'+str((n + 1) * M + m+1), intfName2='eth-r'+str((n + 1) * M + m+1)+'r'+str(n * M + m+1), bw=10, delay='1ms')
                ISLs [n * M + m][(n + 1) * M + m] = isl2
                ISLs_origin [n * M + m][(n + 1) * M + m] = isl2

    info('myNet ends\n')
    net.start()
    info('**********NET zebra and isisd*******************')
    for n in range(0, N): 
        for m in range(0, M):
            sats[n * M + m].cmd('cd /tmp')
            sats[n * M + m].cmd('touch vtysh.conf')

            #ZEBRA: [XNZM2-2XF6G][EC 100663303] Can't create pid lock file /tmp/r53zebra.interface (Permission denied), exiting
            #sats[n * M + m].cmd('touch r'+ str(n * M + m)+'zebra.api')
            #sats[n * M + m].cmd('touch r'+ str(n * M + m)+'zebra.interface')
            #sats[n * M + m].cmd('touch r'+ str(n * M + m)+'isisd.api')
            #sats[n * M + m].cmd('touch r'+ str(n * M + m)+'isisd.interface')
            
            sat_cmd1 = 'mkdir r'+str(n * M + m+1)
            sats[n * M + m].cmd(sat_cmd1)
            sat_cmd2 = 'cd r'+str(n * M + m+1)
            sats[n * M + m].cmd(sat_cmd2)
            sats[n * M + m].cmd('touch isisd.vty')
            sats[n * M + m].cmd('touch r'+str(n * M + m+1)+'isisd.conf')
            sats[n * M + m].cmd('touch r'+str(n * M + m+1)+'zebra.conf')
            conf_filename1 = '/tmp/r'+str(n * M + m+1)+'/r'+str(n * M + m+1)+'isisd.conf'
            f1 = open(conf_filename1,'w')
            f1.write('hostname r'+str(n * M + m+1)+'\n')
            f1.write('password foo\n')
            f1.write('enable password foo\n')
            f1.write('log stdout\n')
            f1.write('router isis DEAD\n')
            if (n * M + m+1)<=9:
                f1.write('    net 47.0023.0000.0000.0000.0000.0000.0000.000'+str(n * M + m+1)+'.00\n')
            if (n * M + m+1)>9:
                f1.write('    net 47.0023.0000.0000.0000.0000.0000.0000.00'+str(n * M + m+1)+'.00\n')

            f1.write('interface lo\n')
            f1.write('    ip router isis DEAD\n')
            #intfName1='eth-r'+str(n * M + m)+'r'+str(n * M + (m + 1) % M), intfName2='eth-r'+str(n * M + (m + 1) % M)+'r'+str(n * M + m), bw=10, delay='1ms')
            f1.write('interface eth-r'+str(n * M + m+1)+'r'+str(n * M + (m + 1) % M+1)+'\n')
            f1.write('    ip router isis DEAD\n')
            #addlink建立链接是相互的，这里需要反推当目前路由属于被链接时的情况(用循环寻找一遍)
            for n1 in range(0, N): 
                for m1 in range(0, M):
                    if((n1*M+(m1+1)%M)==n * M + m):    #反推确定被链接
                        f1.write('interface eth-r'+str(n * M + m+1)+'r'+str(n1 * M + m1+1)+'\n')
                        f1.write('    ip router isis DEAD\n')
                        continue
            if (n != N - 1) :  # N-1说明没有跨缝的ISL
#intfName1='eth-r'+str(n * M + m)+'r'+str((n + 1) * M + m), intfName2='eth-r'+str((n + 1) * M + m)+'r'+str(n * M + m), bw=10, delay='1ms')
                f1.write('interface eth-r'+str(n * M + m+1)+'r'+str((n + 1) * M + m+1)+'\n')
                f1.write('    ip router isis DEAD\n')
            #当没有跨缝的ISL时，反向推*******
            for n12 in range(0, N): 
                for m12 in range(0, M):
                    if(n12!=(N-1)):    #反推确定被链接
                        if(((n12+1)*M+m12)==n*M+m):
                            f1.write('interface eth-r'+str(n * M + m+1)+'r'+str(n12 * M + m12+1)+'\n')
                            f1.write('    ip router isis DEAD\n')
                            continue
            #没有跨缝反向推
            #f1.write('interface eth-r'+str(n * M + m+)+'h'+str(n * M + m)+'\n')
            f1.write('    ip router isis DEAD\n')
            f1.close()

            conf_filename2 = '/tmp/r'+str(n * M + m+1)+'/r'+str(n * M + m+1)+'zebra.conf'
            f2 = open(conf_filename2,'w')
            #zebra -f r1zebra.conf -d -z /tmp/r1zebra.api -i /tmp/r1zebra.interface --vty_socket /tmp/r1 -u root
            f2.write('hostname r'+str(n * M + m+1)+'\n')
            f2.write('log stdout\n')
            #f2.write('configure terminal\n')
            f2.write('interface lo\n')
            
            #f2.write('ip address 1.1.1.1/32\n')
            f2.write('    ip address '+str(n * M + m+1)+'.'+str(n * M + m+1)+'.'+str(n * M + m+1)+'.'+str(n * M + m+1)+'/32\n')
            f2.write('interface eth-r'+str(n * M + m+1)+'r'+str(n * M + (m + 1) % M+1)+'\n')
            if((n * M + m+1)<(n * M + (m + 1) % M+1)):
                f2.write('    ip address 192.'+str(n * M + m+1)+'.'+str(n * M + (m + 1) % M+1)+'.'+str(n * M + m+1)+'/24\n')
            if((n * M + m+1)>(n * M + (m + 1) % M+1)):
                f2.write('    ip address 192.'+str(n * M + (m + 1) % M+1)+'.'+str(n * M + m+1)+'.'+str(n * M + m+1)+'/24\n')
            #addlink建立链接是相互的，这里需要反推当目前路由属于被链接时的情况(用循环寻找一遍)
            for n2 in range(0, N): 
                for m2 in range(0, M):
                    if((n2*M+(m2+1)%M)==n * M + m):    #反推确定被链接
                        f2.write('interface eth-r'+str(n * M + m+1)+'r'+str(n2 * M + m2+1)+'\n')
                        if((n * M + m+1)<(n2 * M + m2+1)):
                            f2.write('    ip address 192.'+str(n * M + m+1)+'.'+str(n2 * M + m2+1)+'.'+str(n * M + m+1)+'/24\n')
                        if((n * M + m+1)>(n2 * M + m2+1)):
                            f2.write('    ip address 192.'+str(n2 * M + m2+1)+'.'+str(n * M + m+1)+'.'+str(n * M + m+1)+'/24\n')
                        continue
            if (n != N - 1) :  # N-1说明没有跨缝的ISL
#intfName1='eth-r'+str(n * M + m)+'r'+str((n + 1) * M + m), intfName2='eth-r'+str((n + 1) * M + m)+'r'+str(n * M + m), bw=10, delay='1ms')
                f2.write('interface eth-r'+str(n * M + m+1)+'r'+str((n + 1) * M + m+1)+'\n')
                if((n * M + m+1)<((n + 1) * M + m+1)):
                    f2.write('    ip address 192.'+str(n * M + m+1)+'.'+str((n + 1) * M + m+1)+'.'+str(n * M + m+1)+'/24\n')
                else:
                    f2.write('    ip address 192.'+str((n + 1) * M + m+1)+'.'+str(n * M + m+1)+'.'+str(n * M + m+1)+'/24\n')
            #当没有跨缝的ISL时，反向推**********************
            for n22 in range(0, N): 
                for m22 in range(0, M):
                    if(n22!=(N-1)):    #反推确定被链接
                        if(((n22+1)*M+m22)==n*M+m):
                            f2.write('interface eth-r'+str(n * M + m+1)+'r'+str(n22 * M + m22+1)+'\n')
                            if((n * M + m+1)<(n22 * M + m22+1)):
                                f2.write('    ip address 192.'+str(n * M + m+1)+'.'+str(n22 * M + m22+1)+'.'+str(n * M + m+1)+'/24\n')
                            if((n * M + m+1)>(n22 * M + m22+1)):
                                f2.write('    ip address 192.'+str(n22 * M + m22+1)+'.'+str(n * M + m+1)+'.'+str(n * M + m+1)+'/24\n')
                            continue
            #没有跨缝******************
            #f2.write('interface eth-r'+str(n * M + m)+'h'+str(n * M + m)+'\n')
            #f2.write('    ip address 192.168.12'+str(n * M + m)+'/24\n')
            f2.write('ip forwarding\n')
            f2.write('line vty\n')
            f2.close()

            sats[n*M+m].cmd('export PATH=/usr/lib/frr:$PATH')

            sat_cmd3 = 'zebra -f /tmp/r'+str(n * M + m+1)+'/r'+str(n * M + m+1)+'zebra.conf -d -z /tmp/r'+str(n * M + m+1)+'zebra.api -i /tmp/r'+str(n * M + m+1)+'zebra.interface --vty_socket /tmp/r'+str(n * M + m+1)+' -u root'
            print(sat_cmd3)
            ret = sats[n * M + m].cmd(sat_cmd3)
            print(ret)
            time.sleep(0.1)

            sat_cmd4 = 'isisd -f /tmp/r'+str(n * M + m+1)+'/r'+str(n * M + m+1)+'isisd.conf -d -z /tmp/r'+str(n * M + m+1)+'zebra.api -i /tmp/r'+str(n * M + m+1)+'isisd.interface --vty_socket /tmp/r'+str(n * M + m+1)+' -u root'
            print(sat_cmd4)
            ret = sats[n * M + m].cmd(sat_cmd4) 
            print(ret)
            time.sleep(0.1)
    with open('topology.savi', 'w') as f:
        for n in range(num):
            f.write(f'node r{n+1}\n')
        for i in ISLs_origin:
            for j in ISLs_origin[i]:
                f.write(f'link r{i+1}-r{j+1}\n')
    
    info('Savi topology file generated.\n')

            #CLI( net )
            #net.stop()
            #os.system("killall -9 isisd zebra")	
            #os.system("rm -f *api*")		
            #os.system("rm -f *interface*")	
#####################lp
class LinuxRouter( Node ):
    "A Node with IP forwarding enabled."

    def config( self, **params ):
        super( LinuxRouter, self).config( **params )
        # Enable forwarding on the router
        self.cmd( 'sysctl net.ipv4.ip_forward=1' )
        self.cmd( 'sysctl net.ipv6.conf.all.forwarding=1' )

    def terminate( self ):
        self.cmd( 'sysctl net.ipv4.ip_forward=0' )
        self.cmd( 'sysctl net.ipv6.conf.all.forwarding=0' )
        super( LinuxRouter, self ).terminate()

class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

if __name__ == '__main__':
    setLogLevel('info')
    info('*** Scratch network demo (kernel datapath)\n')
    net = Mininet(controller=None, switch=OVSSwitch, link=Link)  # no controller
    info('--cx----111---------------------------\n')
    
    # 启动服务器线程
    def start_server():
        server = ReusableThreadingTCPServer(('127.0.0.1', 12345), Myserver)
        server.serve_forever()
    
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()
    
    # 启动geomview
    def start_geomview():
        time.sleep(5)  # 等待网络初始化完成
        subprocess.run(['sudo', 'geomview', '-run', './savi'])
    
    geomview_thread = threading.Thread(target=start_geomview)
    geomview_thread.start()
    
    CLI(net)  # 进入Mininet命令行交互
    net.stop()
