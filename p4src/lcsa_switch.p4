/* -*- P4_16 -*- */
/*
 * lcsa_switch.p4 — LCSA 卫星交换机数据平面
 *
 * 功能：
 *   1. 标准 IPv4 转发（基础路由）
 *   2. LCSA 报文头解析（格网编码、卫星标识、优先级）
 *   3. 基于格网编码的 LPM 转发
 *   4. 备用下一跳快速切换
 *
 * 报文格式：
 *   Ethernet | IPv4 | LCSA (可选) | Payload
 *   LCSA 通过 IPv4 protocol 字段 253 (实验用) 标识
 */

#include <core.p4>
#include <v1model.p4>

/* 常量 */
const bit<16> TYPE_IPV4 = 0x0800;
const bit<8>  PROTO_LCSA = 253;  /* 实验性协议号 */

/* 类型定义 */
typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<8>    diffserv;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

/* LCSA 自定义报文头 */
header lcsa_t {
    bit<16> src_satellite_id;    /* 源接入卫星 */
    bit<16> dst_satellite_id;    /* 目的接入卫星 */
    bit<32> grid_code;           /* 目的格网编码 */
    bit<8>  priority;            /* 优先级 */
    bit<8>  flags;               /* 标志位: bit0=覆盖有效, bit1=预测覆盖 */
}

struct metadata {
    bit<1> is_lcsa;              /* 是否为 LCSA 报文 */
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    lcsa_t     lcsa;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    state start {
        transition parse_ethernet;
    }

    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            PROTO_LCSA: parse_lcsa;
            default: accept;
        }
    }

    state parse_lcsa {
        packet.extract(hdr.lcsa);
        meta.is_lcsa = 1;
        transition accept;
    }
}

/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

control MyVerifyChecksum(inout headers hdr, inout metadata meta) {
    apply { }
}

/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    action drop() {
        mark_to_drop(standard_metadata);
    }

    /* 标准 IPv4 转发 */
    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    /* 基于格网编码的转发 */
    action grid_forward(macAddr_t dstAddr, egressSpec_t port,
                        bit<16> next_satellite_id) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.lcsa.dst_satellite_id = next_satellite_id;
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    /* 备用路径切换 */
    action switch_backup(macAddr_t dstAddr, egressSpec_t port,
                         bit<16> backup_satellite_id) {
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        hdr.lcsa.dst_satellite_id = backup_satellite_id;
        hdr.lcsa.flags = hdr.lcsa.flags | 0x04; /* 标记已切换 */
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }

    /* 标准 IPv4 LPM 表 */
    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = drop();
    }

    /* LCSA 格网编码转发表 */
    table grid_forwarding {
        key = {
            hdr.lcsa.grid_code: lpm;
            hdr.lcsa.priority: exact;
        }
        actions = {
            grid_forward;
            switch_backup;
            drop;
            NoAction;
        }
        size = 4096;
        default_action = drop();
    }

    /* LCSA 目的卫星直接转发表 */
    table satellite_forwarding {
        key = {
            hdr.lcsa.dst_satellite_id: exact;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction;
        }
        size = 256;
        default_action = drop();
    }

    apply {
        if (hdr.ipv4.isValid()) {
            if (hdr.lcsa.isValid()) {
                /* LCSA 报文：先查格网表，再查卫星表 */
                if (!grid_forwarding.apply().hit) {
                    satellite_forwarding.apply();
                }
            } else {
                /* 普通 IPv4 报文 */
                ipv4_lpm.apply();
            }
        }
    }
}

/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    apply { }
}

/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(
            hdr.ipv4.isValid(),
            { hdr.ipv4.version,
              hdr.ipv4.ihl,
              hdr.ipv4.diffserv,
              hdr.ipv4.totalLen,
              hdr.ipv4.identification,
              hdr.ipv4.flags,
              hdr.ipv4.fragOffset,
              hdr.ipv4.ttl,
              hdr.ipv4.protocol,
              hdr.ipv4.srcAddr,
              hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum,
            HashAlgorithm.csum16);
    }
}

/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.lcsa);
    }
}

/*************************************************************************
***********************  S W I T C H  ***********************************
*************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
