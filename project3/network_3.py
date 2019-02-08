'''
Created on Oct 12, 2016
@author: mwittie
'''
import queue
import threading


## wrapper class for a queue of packets
class Interface:
    ## @param maxsize - the maximum size of the queue storing packets
    def __init__(self, maxsize=0):
        self.queue = queue.Queue(maxsize);
        self.mtu = None

    ##get packet from the queue interface
    def get(self):
        try:
            return self.queue.get(False)
        except queue.Empty:
            return None

    ##put the packet into the interface queue
    # @param pkt - Packet to be inserted into the queue
    # @param block - if True, block until room in queue, if False may throw queue.Full exception
    def put(self, pkt, block=False):
        self.queue.put(pkt, block)


## Implements a network layer packet (different from the RDT packet
# from programming assignment 2).
# NOTE: This class will need to be extended to for the packet to include
# the fields necessary for the completion of this assignment.
class NetworkPacket:
    ## packet encoding lengths
    #address length is the first 10 numbers
    src_addr_S_length = 5   #allow source address to be 5 digits long
    dst_addr_S_length = 5   #allow for addresses up to 5 digits in length
    #the flag indicating whether the packet is segmented is the 6th number (pkt_S[5])
    seg_flag_S_length = 1   #flag length is one
    #the flag indicating the offset, or the packet ID is 2 numbers long, found at pkt_S[6:7]
    offset_S_length = 2     #offset length is 2 (basically the packet id)

    ##@param dst_addr: address of the destination host
    # @param data_S: packet payload
    def __init__(self, src_addr, dst_addr, seg_flag, offset, data_S):
        self.src_addr = src_addr
        self.dst_addr = dst_addr
        self.data_S = data_S
        self.seg_flag = seg_flag        #flag = 0 -> not a segment, flag = 1 -> a segment, flag = 2 -> last segment required to reconstruct
        self.offset = offset            #packet_id

    ## called when printing the object
    def __str__(self):
        return self.to_byte_S()

    ## convert packet to a byte string for transmission over links
    def to_byte_S(self):
        byte_S = str(self.src_addr).zfill(self.src_addr_S_length)
        byte_S += str(self.dst_addr).zfill(self.dst_addr_S_length)
        byte_S += str(self.seg_flag).zfill(self.seg_flag_S_length)
        byte_S += str(self.offset).zfill(self.offset_S_length)
        byte_S += self.data_S
        return byte_S

    ## extract a packet object from a byte string
    # @param byte_S: byte string representation of the packet
    @classmethod
    def from_byte_S(self, byte_S):   #Create header string for addr, offset, flag, data
        src_addr = int(byte_S[0 : NetworkPacket.src_addr_S_length])
        dst_addr = int(byte_S[NetworkPacket.src_addr_S_length : NetworkPacket.src_addr_S_length + NetworkPacket.dst_addr_S_length])
        seg_flag = int(byte_S[NetworkPacket.src_addr_S_length + NetworkPacket.dst_addr_S_length : NetworkPacket.src_addr_S_length + NetworkPacket.dst_addr_S_length + NetworkPacket.seg_flag_S_length])
        offset = int(byte_S[NetworkPacket.src_addr_S_length + NetworkPacket.dst_addr_S_length + NetworkPacket.seg_flag_S_length : NetworkPacket.src_addr_S_length + NetworkPacket.dst_addr_S_length + NetworkPacket.seg_flag_S_length + NetworkPacket.offset_S_length])
        data_S = byte_S[NetworkPacket.src_addr_S_length + NetworkPacket.dst_addr_S_length + NetworkPacket.seg_flag_S_length + NetworkPacket.offset_S_length:]
        return self(src_addr, dst_addr, seg_flag, offset, data_S)


## Implements a network host for receiving and transmitting data
class Host:
    ##@param addr: address of this node represented as an integer
    def __init__(self, addr):
        self.addr = addr
        self.in_intf_L = [Interface()]
        self.out_intf_L = [Interface()]
        self.stop = False #for thread termination
        self.packet_id = 10 #first packet id is 10 by default. Increments by 10
        self.segments = []
        self.reconstructed_packet = ''

    ## called when printing the object
    def __str__(self):
        return 'Host_%s' % (self.addr)

    ## create a packet and enqueue for transmission
    # @param dst_addr: destination address for the packet
    # @param data_S: data being transmitted to the network layer
    def udt_send(self, dst_addr, data_S):
        if len(data_S) > self.out_intf_L[0].mtu:                                #packet is bigger than max transmission size
            length = self.out_intf_L[0].mtu - 13                                #the addresses length is 13, so subtract that from mtu
            #print(len(data_S))
            if len(data_S) % self.out_intf_L[0].mtu != 0:   #if the length of the message doesn't evenly divide by the max transmission size, round up a packet
                num_packets = int(len(data_S) / length) + 1
            #print(num_packets)
            packets=[]  #create empty packet array to store the broken down packets
            for i in range(num_packets):
                if(i == num_packets-1):     #if last packet is being sent after being broken down, change flag to '2' to indicate this
                    packet = NetworkPacket(self.addr, dst_addr, 2, self.packet_id, data_S[:length])
                    self.out_intf_L[0].put(packet.to_byte_S())
                    print('%s: sending packet "%s" on the out interface with mtu=%d' % (self, packet, self.out_intf_L[0].mtu))
                    data_S = data_S[length:]
                else:   #otherwise, send with a '1' flag to indicate it is a segment
                    packet = NetworkPacket(self.addr, dst_addr, 1, self.packet_id, data_S[:length])
                    self.out_intf_L[0].put(packet.to_byte_S())
                    print('%s: sending packet "%s" on the out interface with mtu=%d' % (self, packet, self.out_intf_L[0].mtu))
                    data_S = data_S[length:]
            self.packet_id += 10
            if self.packet_id >= 100:      #reset the packet_id if it breaks 100 since the size is only 2 digits
                self.packet_id = 10
        else:
            p = NetworkPacket(self.addr, dst_addr, 0, self.packet_id, data_S)
            self.out_intf_L[0].put(p.to_byte_S()) #send packets always enqueued successfully
            print('%s: sending packet "%s" on the out interface with mtu=%d' % (self, p, self.out_intf_L[0].mtu))

    #method for reconstructing the packets at the end of the transmission of a group of packets
    def reconstruct(self, segments, id):
        original_data = ''
        for seg in segments:
            if seg[11:13] == id: #check packet_id to make sure they match before putting them together
                original_data += seg[13:]
        return original_data
#I will build a great, great wall on our Southern Border. 2 packets host1-routerA link
#I will build a great, great wall our Southern borde
#
    ## receive packet from the network layer                                    #will probably need another method for reconstructing packets as well
    def udt_receive(self):                                                      #need to check if packet is a segment, and then reconstruct
        pkt_S = self.in_intf_L[0].get()
        if pkt_S is not None:
            print('%s: received packet "%s" on the in interface' % (self, pkt_S))
            current_packet_id = pkt_S[11:13]
            if pkt_S[10] == '1':                                                 #check if packet is segment of a larger packet, if it is, add it to array
                self.segments.append(pkt_S)
            elif pkt_S[10] == '2':                                               #check if received packet is the last packet being received of the same packet_id
                self.segments.append(pkt_S)
                original_data = self.reconstruct(self.segments, current_packet_id)  #construct the original message
                original_packet = NetworkPacket(pkt_S[0:5], pkt_S[5:10], 0, current_packet_id, original_data) #construct the origin packet with the message
                print('#---------------------------------------------------------------------')
                print('%s: successfully reconstructed packet "%s" on the in interface' % (self, original_packet))
                print('#---------------------------------------------------------------------')
                #print(current_packet_id)

    ## thread target for the host to keep receiving data
    def run(self):
        print (threading.currentThread().getName() + ': Starting')
        while True:
            #receive data arriving to the in interface
            self.udt_receive()
            #terminate
            if(self.stop):
                print (threading.currentThread().getName() + ': Ending')
                return



## Implements a multi-interface router described in class
class Router:

    ##@param name: friendly router name for debugging
    # @param intf_count: the number of input and output interfaces
    # @param max_queue_size: max queue length (passed to Interface)
    def __init__(self, name, intf_count, max_queue_size, dict):
        self.stop = False #for thread termination
        self.name = name
        #create a list of interfaces
        self.in_intf_L = [Interface(max_queue_size) for _ in range(intf_count)]
        self.out_intf_L = [Interface(max_queue_size) for _ in range(intf_count)]
        self.dict = dict

    ## called when printing the object
    def __str__(self):
        return 'Router_%s' % (self.name)

    ## look through the content of incoming interfaces and forward to
    # appropriate outgoing interfaces
    def forward(self):                                                          #TODO implement the forwarding decision making down below where indicated. Right now it only forwards the first half of packet
        for i in range(len(self.in_intf_L)):                                    #TODO the segmentation. We need to split the two packets into segments here
            pkt_S = None
            try:
                #get packet from interface i
                pkt_S = self.in_intf_L[i].get()
                #if packet exists make a forwarding decision
                if pkt_S is not None:
                    p = NetworkPacket.from_byte_S(pkt_S) #parse a packet out
                    #segmenting to account for 30mtu between router and server. Copied code from udt_send

                    #ROUTING
                    src_addr = p.src_addr                #source address
                    interface = self.route(src_addr, self.name)     #find correct route with the route method

                    data_S = pkt_S[13:]
                    packet_id = pkt_S[11:13]
                    if len(pkt_S) > self.out_intf_L[i].mtu:
                        length = self.out_intf_L[i].mtu - 13                                #the addresses length is 8, so subtract that from mtu
                        if len(data_S) % self.out_intf_L[i].mtu != 0:   #if the length of the message doesn't evenly divide by the max transmission size, round up a packet
                            num_packets = int(len(data_S) / length) + 1
                        packets=[]  #create empty packet array to store the broken down packets
                        for j in range(num_packets):
                            if(j == num_packets-1):     #if last packet is being sent after being broken down, change flag to '2' to indicate this
                                packet = NetworkPacket(src_addr, interface, 2, packet_id, data_S[:length])
                                self.out_intf_L[interface].put(packet.to_byte_S())
                                print('%s: sending packet "%s" on the out interface with mtu=%d' % (self, packet, self.out_intf_L[i].mtu))
                                data_S = data_S[length:]
                            else:   #otherwise, send with a '1' flag to indicate it is a segment
                                packet = NetworkPacket(src_addr, interface, 1, packet_id, data_S[:length])
                                self.out_intf_L[interface].put(packet.to_byte_S())
                                print('%s: sending packet "%s" on the out interface with mtu=%d' % (self, packet, self.out_intf_L[i].mtu))
                                data_S = data_S[length:]

                    self.out_intf_L[i].put(p.to_byte_S(), True)
                    print('%s: forwarding packet "%s" from interface %d to %d with mtu %d' \
                        % (self, p, i, i, self.out_intf_L[i].mtu))
            except queue.Full:
                print('%s: packet "%s" lost on interface %d' % (self, p, i))
                pass

    def route(self, src_addr, my_name):   #route function to find which route to take to get to the correct host
        if(len(self.in_intf_L) == 1):   #if the length of interfaces is 0, default to the 0 output interface
            return 0
        else:
            interface = 0   #set initial interface to 0

        interface_dict = self.dict[src_addr]
        interface = interface_dict[my_name]

        return interface

    ## thread target for the host to keep forwarding data
    def run(self):
        print (threading.currentThread().getName() + ': Starting')
        while True:
            self.forward()
            if self.stop:
                print (threading.currentThread().getName() + ': Ending')
                return
