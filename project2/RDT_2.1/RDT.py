import Network
import argparse
from time import sleep
import time
import hashlib
class Packet:
   ## the number of bytes used to store packet length
   seq_num_S_length = 10
   length_S_length = 10
   ## length of md5 checksum in hex
   checksum_length = 32
        
   def __init__(self, seq_num, msg_S):
      self.seq_num = seq_num
      self.msg_S = msg_S
        
   @classmethod
   def from_byte_S(self, byte_S):
      if Packet.corrupt(byte_S):
         raise RuntimeError('Cannot initialize Packet: byte_S is corrupt')
      #extract the fields
      seq_num = int(byte_S[Packet.length_S_length : Packet.length_S_length+Packet.seq_num_S_length])
      msg_S = byte_S[Packet.length_S_length+Packet.seq_num_S_length+Packet.checksum_length :]
      return self(seq_num, msg_S)
        
        
   def get_byte_S(self):
      #convert sequence number of a byte field of seq_num_S_length bytes
      seq_num_S = str(self.seq_num).zfill(self.seq_num_S_length)
      #convert length to a byte field of length_S_length bytes
      length_S = str(self.length_S_length + len(seq_num_S) + self.checksum_length + len(self.msg_S)).zfill(self.length_S_length)
      #compute the checksum
      checksum = hashlib.md5((length_S+seq_num_S+self.msg_S).encode('utf-8'))
      checksum_S = checksum.hexdigest()
      #compile into a string
      return length_S + seq_num_S + checksum_S + self.msg_S
   
    
   @staticmethod
   def corrupt(byte_S):
      #extract the fields
      length_S = byte_S[0:Packet.length_S_length]
      seq_num_S = byte_S[Packet.length_S_length : Packet.seq_num_S_length+Packet.seq_num_S_length]
      checksum_S = byte_S[Packet.seq_num_S_length+Packet.seq_num_S_length : Packet.seq_num_S_length+Packet.length_S_length+Packet.checksum_length]
      msg_S = byte_S[Packet.seq_num_S_length+Packet.seq_num_S_length+Packet.checksum_length :]
        
      #compute the checksum locally
      checksum = hashlib.md5(str(length_S+seq_num_S+msg_S).encode('utf-8'))
      computed_checksum_S = checksum.hexdigest()
      #and check if the same
      return checksum_S != computed_checksum_S
        
class RDT:
   ## latest sequence number used in a packet
   seq_num = 1
   ## buffer of bytes read from network
   byte_buffer = '' 
   def __init__(self, role_S, server_S, port):
      self.network = Network.NetworkLayer(role_S, server_S, port)
    
   def disconnect(self):
      self.network.disconnect()
        
   def rdt_1_0_send(self, msg_S):
      p = Packet(self.seq_num, msg_S)
      self.seq_num += 1
      self.network.udt_send(p.get_byte_S())
        
   def rdt_1_0_receive(self):
      ret_S = None
      byte_S = self.network.udt_receive()
      self.byte_buffer += byte_S
      #keep extracting packets - if reordered, could get more than one
      while True:
         #check if we have received enough bytes
         if(len(self.byte_buffer) < Packet.length_S_length):
               return ret_S #not enough bytes to read packet length
         #extract length of packet
         length = int(self.byte_buffer[:Packet.length_S_length])
         if len(self.byte_buffer) < length:
               return ret_S #not enough bytes to read the whole packet
         #create packet from buffer content and add to return string
         p = Packet.from_byte_S(self.byte_buffer[0:length])
         ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
         #remove the packet bytes from the buffer
         self.byte_buffer = self.byte_buffer[length:]
         #if this was the last packet, will return on the next iteration
            
    
   def rdt_2_1_send(self, msg_S):
       p = Packet(self.seq_num, msg_S)
       cur_seq_num = self.seq_num
       while (cur_seq_num == self.seq_num):
           
             self.network.udt_send(p.get_byte_S())
             message = ''

             while (message == ''):
                     message = self.network.udt_receive()

             length = int(message[:Packet.length_S_length])
             
             self.byte_buffer = message[length:]
             if not (Packet.corrupt(message[:length])):
                     response_pkt = Packet.from_byte_S(message[:length])
                     #Check for previous packet number
                     if (response_pkt.seq_num < self.seq_num):
                              #Resend an ACK to acknowledge received pkt
                              ACK = Packet(response_pkt.seq_num, "ACK")
                              self.network.udt_send(ACK.get_byte_S())
                     #Check for ACK
                     elif (response_pkt.msg_S == "ACK"):
                              #Can move on to sending next packet
                              print("recieved ACK")
                              self.seq_num += 1
                     #Check for NAK
                     elif (response_pkt.msg_S == "NAK"):
                              print("recieved NAK, resend data")
                              self.byte_buffer = ''
             else:
                     self.byte_buffer = ''

   
   def rdt_2_1_receive(self):
       ret_S = None
       byte_S = self.network.udt_receive()
       self.byte_buffer += byte_S

       #Variable for current packet number
       cur_seq_num = self.seq_num

       #keep extracting packets - if reordered, could get more than one
       while (cur_seq_num == self.seq_num):
           #check if we have received enough bytes
           if(len(self.byte_buffer) < Packet.length_S_length):
               #not enough bytes to read packet length
               #return ret_S
               break
           #extract length of packet
           length = int(self.byte_buffer[:Packet.length_S_length])
           if len(self.byte_buffer) < length:
               #not enough bytes to read the whole packet
               #return ret_S
               break
           #Check if corrupt packet
           if Packet.corrupt(self.byte_buffer):
               #If corrupt, send NAK
               print("data corrupted, sent NAK")
               NAK = Packet(self.seq_num, "NAK")
               self.network.udt_send(NAK.get_byte_S())

           #If Packet not corrupt
           else:
               #create packet from buffer content and add to return string
               p = Packet.from_byte_S(self.byte_buffer[0:length])

               #Check if packet is an ACK or NAK
               if (p.msg_S == "NAK" or p.msg_S == "ACK"):
                   self.byte_buffer = self.byte_buffer[length:]
                   continue
               #Check for previous packet number
               if (p.seq_num < self.seq_num):
                   #This means we have already received this packet
                   #So send another ACK about received packet
                   ACK = Packet(p.seq_num, "ACK")
                   print("duplicate packet, resend ACK")
                   self.network.udt_send(ACK.get_byte_S())
               #Else if packet matches number we are looking for
               elif (p.seq_num == self.seq_num):
                   #NEW PACKET FRICK YEAH
                   #Send ACK on new packet
                   print("data not corrupted, sent ACK")
                   ACK = Packet(self.seq_num, "ACK")
                   self.network.udt_send(ACK.get_byte_S())
                   #Increment for next packet number
                   self.seq_num += 1

               ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
           #remove the packet bytes from the buffer
           self.byte_buffer = self.byte_buffer[length:]
           #if this was the last packet, will return on the next iteration
       return ret_S
    
   def rdt_3_0_send(self, msg_S):
       p = Packet(self.seq_num, msg_S)
       cur_seq_num = self.seq_num
       while (cur_seq_num == self.seq_num):
             self.network.udt_send(p.get_byte_S())
             message = ''
             initial_time = time.time()
             time_allowed = 3
            
             while (message == '' and initial_time+time_allowed>=time.time()):
                     message = self.network.udt_receive()

             if message =='':
                 print("timeout: resend data")
                 continue
            
             length = int(message[:Packet.length_S_length])
             self.byte_buffer = message[length:]
             if not (Packet.corrupt(message[:length])):
                     response_pkt = Packet.from_byte_S(message[:length])
                     #Check for previous packet number
                     if (response_pkt.seq_num < self.seq_num):
                              #Resend an ACK to acknowledge received pkt
                              ACK = Packet(response_pkt.seq_num, "ACK")
                              self.network.udt_send(ACK.get_byte_S())
                     #Check for ACK
                     elif (response_pkt.msg_S == "ACK"):
                              #Can move on to sending next packet
                              print("recieved ACK")
                              self.seq_num += 1
                     #Check for NAK
                     elif (response_pkt.msg_S == "NAK"):
                              print("recieved NAK, resend data")
                              self.byte_buffer = ''
             else:
                     self.byte_buffer = ''
        
   def rdt_3_0_receive(self):
       ret_S = None
       byte_S = self.network.udt_receive()
       self.byte_buffer += byte_S

       #Variable for current packet number
       cur_seq_num = self.seq_num

       #keep extracting packets - if reordered, could get more than one
       while (cur_seq_num == self.seq_num):
           #check if we have received enough bytes
           if(len(self.byte_buffer) < Packet.length_S_length):
               #not enough bytes to read packet length
               #return ret_S
               break
           #extract length of packet
           length = int(self.byte_buffer[:Packet.length_S_length])
           if len(self.byte_buffer) < length:
               #not enough bytes to read the whole packet
               #return ret_S
               break
           #Check if corrupt packet
           if Packet.corrupt(self.byte_buffer):
               print("data corrupted, sent NAK")
               #If corrupt, send NAK
               NAK = Packet(self.seq_num, "NAK")
               self.network.udt_send(NAK.get_byte_S())

           #If Packet not corrupt
           else:
               #create packet from buffer content and add to return string
               p = Packet.from_byte_S(self.byte_buffer[0:length])

               #Check if packet is an ACK or NAK
               if (p.msg_S == "NAK" or p.msg_S == "ACK"):
                   self.byte_buffer = self.byte_buffer[length:]
                   continue
               #Check for previous packet number
               if (p.seq_num < self.seq_num):
                   #This means we have already received this packet
                   #So send another ACK about received packet
                   print("duplicate packet, resend ACK")
                   ACK = Packet(p.seq_num, "ACK")
                   self.network.udt_send(ACK.get_byte_S())
               #Else if packet matches number we are looking for
               elif (p.seq_num == self.seq_num):
                   #NEW PACKET FRICK YEAH
                   #Send ACK on new packet
                   print("data not corrupted, sent ACK")
                   ACK = Packet(self.seq_num, "ACK")
                   self.network.udt_send(ACK.get_byte_S())
                   #Increment for next packet number
                   self.seq_num += 1

               ret_S = p.msg_S if (ret_S is None) else ret_S + p.msg_S
           #remove the packet bytes from the buffer
           self.byte_buffer = self.byte_buffer[length:]
           #if this was the last packet, will return on the next iteration
       return ret_S
                  
        
if __name__ == '__main__':
   parser =  argparse.ArgumentParser(description='RDT implementation.')
   parser.add_argument('role', help='Role is either client or server.', choices=['client', 'server'])
   parser.add_argument('server', help='Server.')
   parser.add_argument('port', help='Port.', type=int)
   args = parser.parse_args()
    
   rdt = RDT(args.role, args.server, args.port)
   if args.role == 'client':
      rdt.rdt_1_0_send('MSG_FROM_CLIENT')
      sleep(2)
      print(rdt.rdt_1_0_receive())
      rdt.disconnect()
        
        
   else:
      sleep(1)
      print(rdt.rdt_1_0_receive())
      rdt.rdt_1_0_send('MSG_FROM_SERVER')
      rdt.disconnect()
        
