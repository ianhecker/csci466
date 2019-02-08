import queue
import threading
import re
from threading import Lock


# wrapper class for a queue of packets
class Interface:

    # @param maxsize - the maximum size of the queue storing packets
    def __init__(self, maxsize=0):
        self.in_queue = queue.Queue(maxsize)
        self.out_queue = queue.Queue(maxsize)

    # get packet from the queue interface
    # @param in_or_out - use 'in' or 'out' interface
    def get(self, in_or_out):
        try:
            if in_or_out == 'in':
                pkt_S = self.in_queue.get(False)
                # if pkt_S is not None:
                #     print('getting packet from the IN queue')
                return pkt_S
            else:
                pkt_S = self.out_queue.get(False)
                # if pkt_S is not None:
                #     print('getting packet from the OUT queue')
                return pkt_S
        except queue.Empty:
            return None

    # put the packet into the interface queue
    # @param pkt - Packet to be inserted into the queue
    # @param in_or_out - use 'in' or 'out' interface
    # @param block - if True, block until room in queue, if False may throw queue.Full exception

    def put(self, pkt, in_or_out, block=False):
        if in_or_out == 'out':
            # print('putting packet in the OUT queue')
            self.out_queue.put(pkt, block)
        else:
            # print('putting packet in the IN queue')
            self.in_queue.put(pkt, block)


# Implements a network layer packet.
class NetworkPacket:
    # packet encoding lengths
    dst_S_length = 5
    prot_S_length = 1

    # @param dst: address of the destination host
    # @param data_S: packet payload
    # @param prot_S: upper layer protocol for the packet (data, or control)
    def __init__(self, dst, prot_S, data_S):
        self.dst = dst
        self.data_S = data_S
        self.prot_S = prot_S

    # called when printing the object
    def __str__(self):
        return self.to_byte_S()

    # convert packet to a byte string for transmission over links
    def to_byte_S(self):
        byte_S = str(self.dst).zfill(self.dst_S_length)
        if self.prot_S == 'data':
            byte_S += '1'
        elif self.prot_S == 'control':
            byte_S += '2'
        else:
            raise ('%s: unknown prot_S option: %s' % (self, self.prot_S))
        byte_S += self.data_S
        return byte_S

    # extract a packet object from a byte string
    # @param byte_S: byte string representation of the packet
    @classmethod
    def from_byte_S(self, byte_S):
        dst = byte_S[0: NetworkPacket.dst_S_length].strip('0')
        prot_S = byte_S[NetworkPacket.dst_S_length: NetworkPacket.dst_S_length + NetworkPacket.prot_S_length]
        if prot_S == '1':
            prot_S = 'data'
        elif prot_S == '2':
            prot_S = 'control'
        else:
            raise ('%s: unknown prot_S field: %s' % (self, prot_S))
        data_S = byte_S[NetworkPacket.dst_S_length + NetworkPacket.prot_S_length:]
        return self(dst, prot_S, data_S)


# Implements a network host for receiving and transmitting data
class Host:

    # @param addr: address of this node represented as an integer
    def __init__(self, addr):
        self.addr = addr
        self.intf_L = [Interface()]
        self.stop = False  # for thread termination

    # called when printing the object
    def __str__(self):
        return self.addr

    # create a packet and enqueue for transmission
    # @param dst: destination address for the packet
    # @param data_S: data being transmitted to the network layer
    def udt_send(self, dst, data_S):
        p = NetworkPacket(dst, 'data', data_S)
        print('%s: sending packet "%s"' % (self, p))
        self.intf_L[0].put(p.to_byte_S(), 'out')  # send packets always enqueued successfully

    # receive packet from the network layer
    def udt_receive(self):
        pkt_S = self.intf_L[0].get('in')
        if pkt_S is not None:
            print('%s: received packet "%s"' % (self, pkt_S))

            p = NetworkPacket.from_byte_S(pkt_S)

            if self.addr is 'H2':
                if re.search('MESSAGE_FROM_H1', p.data_S, flags=0):
                    self.udt_send('H1', 'REPLY_FROM_H2')

    # thread target for the host to keep receiving data
    def run(self):
        print(threading.currentThread().getName() + ': Starting')
        while True:
            # receive data arriving to the in interface
            self.udt_receive()
            # terminate
            if self.stop:
                print(threading.currentThread().getName() + ': Ending')
                return


# Implements a multi-interface router
class Router:

    # @param name: friendly router name for debugging
    # @param cost_D: cost table to neighbors {neighbor: {interface: cost}}
    # @param max_queue_size: max queue length (passed to Interface)
    def __init__(self, name, cost_D, max_queue_size):
        self.stop = False  # for thread termination
        self.name = name
        self.INFINITY = 99999
        # create a list of interfaces
        self.intf_L = [Interface(max_queue_size) for _ in range(len(cost_D))]

        # save neighbors and interfaces on which we connect to them
        self.cost_D = cost_D  # {neighbor: {interface: cost}}
        self.reversed_cost_D = self.reverse_cost_D()
        self.no_interface_cost_D = self.strip_interface_from_cost_D()

        self.rt_tbl_D = self.create_initial_rt_tbl()  # {destination: {router: cost}}
        print('%s: Initialized routing table' % self)
        self.distVectorInitialized = False
        self.print_routes()

    # create initial routing table
    def create_initial_rt_tbl(self):
        rt_tbl_D = {self.name: {self.name: 0}}
        for neighbor in self.cost_D.keys():
            for interface in self.cost_D[neighbor].keys():
                rt_tbl_D[neighbor] = {self.name: self.cost_D[neighbor][interface]}

        return rt_tbl_D

    def initialize_dist_vector(self):
        # for all dest y in N

        for dest in self.rt_tbl_D.keys():
            if dest not in self.cost_D.keys() and dest is not self.name:
                self.rt_tbl_D[dest] = {self.name: self.INFINITY}
            for neighbor in self.cost_D.keys():
                for interface in self.cost_D[neighbor].keys():
                    if dest in self.cost_D.keys() and interface in self.cost_D[dest].keys():
                        self.rt_tbl_D[dest][self.name] = self.cost_D[dest][interface]

                if 'H' not in neighbor:
                    self.rt_tbl_D[dest][neighbor] = self.INFINITY

        for neighbor in self.cost_D.keys():
            for interface in self.cost_D[neighbor].keys():
                self.send_routes(interface)

    def get_neighbor_on_interface(self, interface):
        for neighbor in self.cost_D.keys():
            if interface in self.cost_D[neighbor].keys():

                return neighbor
        pass

    def reverse_cost_D(self):
        reversed_cost_D = {}
        for neighbor in self.cost_D.keys():
            for interface in self.cost_D[neighbor].keys():
                reversed_cost_D[interface] = neighbor

        return reversed_cost_D

    def strip_interface_from_cost_D(self):
        cost = {}
        for neighbor in self.cost_D.keys():
            for interface in self.cost_D[neighbor].keys():
                cost[neighbor] = self.cost_D[neighbor][interface]

        return cost

    # Print routing table
    def print_routes(self):

        destinations = []
        knownRouters = []
        table = self.rt_tbl_D

        for dest in sorted(table.keys()):
            destinations.append(dest)
            for router in sorted(table[dest].keys()):
                knownRouters.append(router)

        columns = len(destinations) - 1
        # PRINT TOP BORDER
        print("|======|", end="", flush=True)
        for x in range(0, columns):
            print("======|", end="", flush=True)
        print("======|")
        print("|", end="", flush=True)

        # PRINT FIRST ROW - DESTINATIONS
        print(" %s   " % self.name, end="", flush=True)
        for dest in destinations:
            print("| %s   " % dest, end='', flush=True)
        print("|")

        # PRINT TOP BORDER - BOTTOM
        print("|======|", end="", flush=True)
        for x in range(0, columns):
            print("======|", end="", flush=True)
        print("======|")

        # PRINT SUBSEQUENT ROWS - KNOWN ROUTERS
        for router in sorted(set(knownRouters)):
            print("| %s  " % router + " ", end='', flush=True)

            for dest in destinations:
                if router in table[dest]:
                    if table[dest][router] == int(-1):
                        print("| ?    ", end='', flush=True)
                    elif table[dest][router] == self.INFINITY:
                        print("| ∞    ", end='', flush=True)
                    else:
                        print("| %s   " % table[dest][router] + " ", end='', flush=True)

            # PRINT DIVIDERS BETWEEN ROWS
            print("|")
            print("|------|", end="", flush=True)
            for x in range(0, columns):
                print("------|", end="", flush=True)
            print("------|")

        # PRINT BOTTOM BORDER
        print("|======|", end="", flush=True)
        for x in range(0, columns):
            print("======|", end="", flush=True)
        print("======|")
        print()


    # called when printing the object
    def __str__(self):
        return self.name

    # look through the content of incoming interfaces and
    # process data and control packets
    def process_queues(self):
        for i in range(len(self.intf_L)):
            pkt_S = None
            # get packet from interface i
            pkt_S = self.intf_L[i].get('in')
            # if packet exists make a forwarding decision
            if pkt_S is not None:
                p = NetworkPacket.from_byte_S(pkt_S)  # parse a packet out
                if p.prot_S == 'data':
                    self.forward_packet(p, i)
                elif p.prot_S == 'control':
                    self.update_routes(p, i)
                else:
                    raise Exception('%s: Unknown packet type in packet %s' % (self, p))

    # forward the packet according to the routing table
    #  @param p Packet to forward
    #  @param i Incoming interface number for packet p
    def forward_packet(self, p, i):
        try:
            # TODO: Here you will need to implement a lookup into the
            # forwarding table to find the appropriate outgoing interface
            # for now we assume the outgoing interface is 1

            # If dest not in our cost_D table, we arent connected to the host.
            # Check routing table for router with lowest advertised path to host
            # Use router as key, and get interface from cost_D
            if p.dst not in self.cost_D.keys():
                # Check rt_tbl_D for the LOWEST cost router from to p.dst
                    # Attempt to use router as key in cost_D to get interface
                        # If works, forward on the interface
                        # If Not in cost_D, get next lowest router and loop again

                # Dictionary of routers with advertised cost to p.dst
                potential_routers = {}

                # Get routers advertised under p.dst
                potential_routers = self.rt_tbl_D[p.dst]
                lowest_cost = self.INFINITY
                router_to_forward = ''

                while potential_routers:
                    for router in potential_routers.keys():
                        if potential_routers[router] < lowest_cost:
                            lowest_cost = potential_routers[router]
                            router_to_forward = router
                    # Check if router is not our neighbor
                    # Loop again to find next lowest advertised cost to p.dst
                    if router_to_forward not in self.cost_D.keys():
                        potential_routers.pop(router_to_forward, None)
                    # Found router that is directly connected to us
                    # Get interface via the cost_D table
                    else:
                        tmp_dict = self.cost_D[router_to_forward]
                        for tmp in tmp_dict:
                            interface = tmp
                        break
            # Best case, this working means the host is connected to us
            # We can simply forward the packet to its final destination
            else:
                tmp_dict = self.cost_D[p.dst]
                for tmp in tmp_dict:
                    interface = tmp

            # print("\nForward PKT name ", self.name)
            # print("Forward PKT DST ", p.dst)
            # print("Forward PKT cost_D ", self.cost_D)
            # print("Forward PKT interface ", interface)

            self.intf_L[interface].put(p.to_byte_S(), 'out', True)
            print('%s: forwarding packet "%s" from interface %d to %d' %
                  (self, p, i, interface))
        except queue.Full:
            print('%s: packet "%s" lost on interface %d' % (self, p, i))
            pass

    # send out route update
    # @param i Interface number on which to send out a routing update
    def send_routes(self, interface):
        # TODO: Send out a routing table update
        if self.distVectorInitialized is False:
            self.distVectorInitialized = True
            self.initialize_dist_vector()
        else:
            # create a routing table update packet

            # Append dictionary into string format
            data_tmp = ''

            for x, y in self.rt_tbl_D.items():
                data_tmp += str(x)
                data_tmp += str(y)

            # remove apostrophese from str translation
            data = data_tmp.replace("'", "")

            p = NetworkPacket(0, 'control', data)
            try:
                print('%s: sending routing update "%s" from interface %d' % (self, p, interface))
                self.intf_L[interface].put(p.to_byte_S(), 'out', True)
            except queue.Full:
                print('%s: packet "%s" lost on interface %d' % (self, p, interface))

    # forward the packet according to the routing table
    #  @param p Packet containing routing information
    def update_routes(self, p, i):
        # TODO: add logic to update the routing tables and possibly send out routing updates
        print('%s: Received routing update %s from interface %d' % (self, p, i))
        interfaceNum = i
        neighbor = self.get_neighbor_on_interface(interfaceNum)
        # Regular Expression to parse out received data storing
        # received string in format: {destination: {router: cost}}
        # finds matches such as:	H1{'RA' : 1, 'H1' : ?, 'RB' : ?} OR RB{'RA' : 1}
        dest_match_arr = re.findall('(\w{2}\{.*?\})', p.data_S, flags=0)

        dest_dict = {}
        router_dict = {}
        if dest_match_arr:
            for i in dest_match_arr:
                # Pulls out double letter name from beginning before the '{'
                destination = i[:2]
                # Pulls out in format 'RA : 1' OR 'RA : -1'
                router_and_cost_arr = re.findall('(?P<router_and_cost>\w{2}\s*:\s*-*\d+)', i, flags=0)

                for j in router_and_cost_arr:
                    # Pulls out double letter name
                    router_tmp = re.match('(\w{2})', j, flags=0)
                    router = router_tmp.group(0)
                    cost = j[4:]

                    router_dict[router] = int(cost)
                    dest_dict[destination] = router_dict

                router_dict = {}

        for dest in dest_dict.keys():
            if dest not in self.rt_tbl_D.keys():
                self.rt_tbl_D[dest] = {self.name: 999}

            distToDest = self.rt_tbl_D[dest][self.name]
            self.rt_tbl_D[dest][neighbor] = dest_dict[dest][neighbor]
            if interfaceNum in self.cost_D[neighbor]:
                if self.no_interface_cost_D[neighbor] + dest_dict[dest][neighbor] < distToDest:
                    updatedDistToDest = self.no_interface_cost_D[neighbor] + dest_dict[dest][neighbor]
                    self.rt_tbl_D[dest][self.name] = updatedDistToDest
                    for interface in self.reversed_cost_D.keys():
                        self.send_routes(interface)

    # thread target for the host to keep forwarding data
    def run(self):
        print(threading.currentThread().getName() + ': Starting')
        while True:
            self.process_queues()
            if self.stop:
                print(threading.currentThread().getName() + ': Ending')
                return
