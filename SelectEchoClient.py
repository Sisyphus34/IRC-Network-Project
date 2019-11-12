from socket import *
import selectors

class MultiEchoClient(object):

    def __init__(self, host="localhost", port=3607, num_connections=3):
        self.sockets = []

        # Create our selector
        self.sel = selectors.DefaultSelector()

        # Create the specified number of sockets, connect them to the server, and register them with select
        for i in range(num_connections):
            # Create a new TCP socket and connect to the server
            sock = socket(AF_INET, SOCK_STREAM)
            sock.connect((host, port))
            
            # Set the socket to non-blocking. This must be done after connecting to the server
            sock.setblocking(False)

            # Append the new socket to our list of sockets
            self.sockets.append(sock)

            # Specify that we only want to look for read events
            events = selectors.EVENT_READ 
            # Associate the index number of this socket with the select event
            data = i
            # Register the socket with select
            self.sel.register(self.sockets[i], events, data)

            print("Registered socket %i" %(i))

    # Continuously loop asking for input from the user
    def run(self):
        while True:
            # Get input
            msg = input("What do you want to send: ")
            # Send this input to the server over each connection
            for s in self.sockets:
                s.send(msg.encode())

            # Read events to process from select
            events = self.sel.select(timeout=10)
            # For each of those events
            for key, mask in events:
                # Extract the socket and the data from key
                sock = key.fileobj
                data = key.data

                # Check to make sure this event indicated the socket is ready to be read
                if mask & selectors.EVENT_READ :
                    # Read the response and print it out, with the value encoded in data appended to the string
                    rsp = sock.recv(2048).decode()
                    print("%s: %i" %(rsp, data))


if __name__ == "__main__":
    multi = MultiEchoClient()
    try:
        multi.run()
    except KeyboardInterrupt:
        print("\r\nThe program was interrupted with a keyboard interrupt.")
    
