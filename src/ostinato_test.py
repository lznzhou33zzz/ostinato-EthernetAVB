#! /usr/bin/env python
# -*- coding: utf-8 -*-
# standard modules
import logging
import os
import sys
import time
import binascii
# ostinato modules
# (user scripts using the installed package should prepend ostinato. i.e
#  ostinato.core and ostinato.protocols)
from ostinato.core import ost_pb, DroneProxy
from ostinato.protocols.mac_pb2 import mac
from ostinato.protocols.vlan_pb2 import vlan, Vlan
from ostinato.protocols.hexdump_pb2 import hexDump, HexDump

def toStr(s):
    return s and chr(atoi(s[:2], base=16)) + toStr(s[2:]) or ''


# initialize defaults
use_defaults = False
host_name = '127.0.0.1'
tx_port_number = 0
rx_port_number = 0

# setup logging
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# command-line option/arg processing
if len(sys.argv) > 1:
    if sys.argv[1] in ('-d', '--use-defaults'):
        use_defaults = True
    if sys.argv[1] in ('-h', '--help'):
        print('%s [OPTION]...' % (sys.argv[0]))
        print('Options:')
        print(' -d --use-defaults   run using default values')
        print(' -h --help           show this help')
        sys.exit(0)

print('')
print('This example expects the following topology -')
print('')
print(' +-------+          +-------+')
print(' |       |Tx--->----|       |')
print(' | Drone |          |  DUT  |')
print(' |       |Rx---<----|       |')
print(' +-------+          +-------+')
print('')
print('Drone has 2 ports connected to DUT. Packets sent on the Tx port')
print('are expected to be received back on the Rx port')
print('')
print('An easy way to simulate the above topology is to select the loopback')
print('port as both Tx and Rx ports')
print('')

if not use_defaults:
    s = raw_input('Drone\'s Hostname/IP [%s]: ' % (host_name))
    host_name = s or host_name

drone = DroneProxy(host_name)

try:
    # connect to drone
    log.info('connecting to drone(%s:%d)'
            % (drone.hostName(), drone.portNumber()))
    drone.connect()

    # retreive port id list
    log.info('retreiving port list')
    port_id_list = drone.getPortIdList()

    # retreive port config list
    log.info('retreiving port config for all ports')
    port_config_list = drone.getPortConfig(port_id_list)

    if len(port_config_list.port) == 0:
        log.warning('drone has no ports!')
        sys.exit(1)

    # print port list and get tx/rx port id
    print('Port List')
    print('---------')
    for port in port_config_list.port:
        print('%d.%s (%s)' % (port.port_id.id, port.name, port.description))
        # use a loopback port as default tx/rx port
        if ('lo' in port.name or 'loopback' in port.description.lower()):
            tx_port_number = port.port_id.id
            rx_port_number = port.port_id.id

    if not use_defaults:
        p = raw_input('Tx Port Id [%d]: ' % (tx_port_number))
        if p:
            tx_port_number = int(p)

        p = raw_input('Rx Port Id [%d]: ' % (rx_port_number))
        if p:
            rx_port_number = int(p)

    tx_port = ost_pb.PortIdList()
    tx_port.port_id.add().id = tx_port_number;

    rx_port = ost_pb.PortIdList()
    rx_port.port_id.add().id = rx_port_number;

    # add a stream
    stream_id = ost_pb.StreamIdList()
    stream_id.port_id.CopyFrom(tx_port.port_id[0])
    stream_id.stream_id.add().id = 1
    log.info('adding tx_stream %d' % stream_id.stream_id[0].id)
    drone.addStream(stream_id)

    # configure the stream
    stream_cfg = ost_pb.StreamConfigList()
    stream_cfg.port_id.CopyFrom(tx_port.port_id[0])
    s = stream_cfg.stream.add()
    s.stream_id.id = stream_id.stream_id[0].id
    s.core.is_enabled = True
    s.control.num_packets = 5

    # setup stream protocols as mac:eth2:ip4:udp:payload
    p = s.protocol.add()
    p.protocol_id.id = ost_pb.Protocol.kMacFieldNumber
    p.Extensions[mac].dst_mac = 0x000EC6C3425F
    p.Extensions[mac].src_mac = 0x001234567800

    p = s.protocol.add()
    p.protocol_id.id = ost_pb.Protocol.kVlanFieldNumber
    vlan = p.Extensions[vlan]
    vlan.vlan_tag = 0x4002

    p = s.protocol.add()
    p.protocol_id.id = ost_pb.Protocol.kHexDumpFieldNumber
    HexDump = p.Extensions[hexDump]
#   tag Protocol Identifier
    TPI= '8100'
#   CFI 1bit 0:Standard MAC package
#   PCP 3bit Priority Code Point  (0=lowest, 7=highest)
    PCP_CFI = '3'
    VlanID = '111'
    P802_1Q_Header = TPI + PCP_CFI + VlanID

    EthType = '22f0'

    subtype = '82'
    Sv_Version = '8'
    R_ntscfDataLength_sequenceNum = '00F00'
    P1722Header = subtype + Sv_Version + R_ntscfDataLength_sequenceNum

    StreamID = '00123456780081ff'

    P802_1Q_Payload = P1722Header + StreamID

#     HexDump.content = AVBData.encode('ascii')
#     HexDump.content = byte(map(ord, "22F08280100000123456780081FF"))
    HexDump.content = binascii.a2b_hex(P802_1Q_Header + EthType + P802_1Q_Payload)


#     s.protocol.add().protocol_id.id = ost_pb.Protocol.kUdpFieldNumber
    s.protocol.add().protocol_id.id = ost_pb.Protocol.kPayloadFieldNumber


    log.info('configuring tx_stream %d' % stream_id.stream_id[0].id)
    drone.modifyStream(stream_cfg)

    # clear tx/rx stats
    log.info('clearing tx/rx stats')
    drone.clearStats(tx_port)
    drone.clearStats(rx_port)

    # start capture and transmit
    log.info('starting capture')
    drone.startCapture(rx_port)
    log.info('starting transmit')
    drone.startTransmit(tx_port)

    # wait for transmit to finish
    log.info('waiting for transmit to finish ...')
    time.sleep(7)

    # stop transmit and capture
    log.info('stopping transmit')
    drone.stopTransmit(tx_port)
    log.info('stopping capture')
    drone.stopCapture(rx_port)

    # get tx/rx stats
    log.info('retreiving stats')
    tx_stats = drone.getStats(tx_port)
    rx_stats = drone.getStats(rx_port)

    #log.info('--> (tx_stats)' + tx_stats.__str__())
    #log.info('--> (rx_stats)' + rx_stats.__str__())
    log.info('tx pkts = %d, rx pkts = %d' %
            (tx_stats.port_stats[0].tx_pkts, rx_stats.port_stats[0].rx_pkts))

    # retrieve and dump received packets
    log.info('getting Rx capture buffer')
    buff = drone.getCaptureBuffer(rx_port.port_id[0])
    drone.saveCaptureBuffer(buff, 'capture.pcap')
    log.info('dumping Rx capture buffer')
    os.system('tshark -r capture.pcap')
    os.remove('capture.pcap')

    # delete streams
    log.info('deleting tx_stream %d' % stream_id.stream_id[0].id)
    drone.deleteStream(stream_id)

    # bye for now
    drone.disconnect()

except Exception as ex:
    log.exception(ex)
    sys.exit(1)