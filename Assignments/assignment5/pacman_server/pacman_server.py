import socket
import sys
import select
from time import sleep

class Network():
    def __init__(self, port):
        self.active_socks = []
        self.half_open_socks = {}
        self.waiting_socks = {}  #socket, indexed by password
        self.waiting_passwords = {} #password, indexed by socket
        self.sock_pairs = {}
        self.logfile = open("logfile.txt", "w+")
        try:
            self.listening_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as err: 
            print("socket creation failed with error %s" %(err), file=self.logfile)
            sys.exit()
        self.__recv_buf = bytes()

        while True:
            try:
                self.listening_sock.bind(('', port))
                break
            except OSError as err:
                print(err, file=self.logfile)
                print("waiting, will retry in 10 seconds", file=self.logfile)
                sleep(10)
  
        # put the socket into listening mode 
        self.listening_sock.listen(5)
        print("listening for incoming connection...", file=self.logfile)
        self.active_socks.append(self.listening_sock)


    def accept_connection(self):
        # Establish connection from client. 
        c_sock, addr = self.listening_sock.accept()
        print('Got connection from', addr, file=self.logfile)
        self.logfile.flush()
        self.half_open_socks[c_sock] = addr
        self.active_socks.append(c_sock)

    def receive_passwd(self, c_sock):
        fd = c_sock.fileno()
        print("receive_passwd, fd=", fd, file=self.logfile)
        msg = c_sock.recv(1024)

        if len(msg) == 0:
            # the connection died - cleanup its state
            print("half open connection died, fd=", fd, file=self.logfile)
            del self.half_open_socks[c_sock]
            self.active_socks.remove(c_sock)
            return
            
        passwd = msg.decode()

        if passwd in self.waiting_socks:
            # password patches that of a waiting connection - join them up
            waiting_sock = self.waiting_socks[passwd]
            wfd = waiting_sock.fileno()
            print("fd ", fd, "passwd ", passwd, "matches fd", wfd, file=self.logfile)
            c_sock.send("OK\n".encode())
            waiting_sock.send("OK\n".encode())
            self.sock_pairs[c_sock] = waiting_sock
            self.sock_pairs[waiting_sock] = c_sock
            del self.waiting_passwords[waiting_sock]
            del self.waiting_socks[passwd]
        else:
            # move connection from half-open to one that has a password and is waiting
            print("fd ", fd, "received passwd ", passwd, file=self.logfile)
            self.waiting_socks[passwd] = c_sock
            self.waiting_passwords[c_sock] = passwd
            del self.half_open_socks[c_sock]

    def relay_message(self, sock):
        #print("relay_message")
        partner_sock = self.sock_pairs[sock]
        try:
            recv_bytes = sock.recv(10000)
            partner_sock.send(recv_bytes)
        except ConnectionResetError:
            sock.close()
            partner_sock.close()
            del self.sock_pairs[sock]
            del self.sock_pairs[partner_sock]
            self.active_socks.remove(sock)
            self.active_socks.remove(partner_sock)

    def check_for_messages(self):
        rd, wd, ed = select.select(self.active_socks, [],[])
        if not rd:
            pass
        else:
            for sock in rd:
                if sock is self.listening_sock:
                    self.accept_connection()
                elif sock in self.sock_pairs:
                    self.relay_message(sock)
                elif sock in self.half_open_socks:
                    self.receive_passwd(sock)
                elif sock in self.waiting_passwords:
                    print("Error: ", sock.fileno(),
                          "got a message from a waiting sock!", file=self.logfile)
                    # no idea what to do, just close it.
                    self.active_socks.remove(sock)
                    sock.close()
                    passwd = self.waiting_passwords[sock]
                    del self.waiting_passwords[sock]
                    del self.waiting_socks[passwd]
                else:
                    print("Got a stray socket!", sock, file=self.logfile)
                    try:
                        sock.close()
                    except:
                        pass
                    

net = Network(9872)

while True:
    net.check_for_messages()
