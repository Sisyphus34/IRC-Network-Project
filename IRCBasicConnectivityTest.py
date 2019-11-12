import threading, os, re, time, sys, json, copy
from optparse import OptionParser


class IRCBasicConnectivityTest():
    
    def __init__(self, IRCServerModule):
        class NewIRCServerModule(IRCServerModule):
            def __init__(self, options, run_on_localhost=False):
                super().__init__(options, run_on_localhost)
                self.sent_messages_asdqw = []
                self.recvd_messages_asdqw = []
                self.special_map = {}


            def process_data(self, select_key, recv_data):
                self.recvd_messages_asdqw.append(recv_data)
            

            def write_data(self, server_name, message):
                try:
                    self.sent_messages_asdqw.append(message)
                    if server_name in self.special_map:
                        key = self.special_map[server_name]
                        self.sel._fd_to_key[key].data.write_buffer = message
                except Exception as e:
                    print(e)


            def connect_to_server(self):
                before_super = copy.deepcopy(list(self.sel._fd_to_key.keys()))
                super().connect_to_server()
                post_super = copy.deepcopy(list(self.sel._fd_to_key.keys()))                
                new_key = self.diff(post_super, before_super)
                if len(new_key) > 0:
                    self.special_map[self.connect_to_host] = new_key[0]
                
                
            def accept_new_connection(self, sock):
                before_super = copy.deepcopy(list(self.sel._fd_to_key.keys()))
                super().accept_new_connection(sock)
                post_super = copy.deepcopy(list(self.sel._fd_to_key.keys()))                
                new_key = self.diff(post_super, before_super)
                if len(new_key) > 0:
                    new_name = self.unknown_server_additions[self.unknown_server_additions_idx]
                    self.unknown_server_additions_idx += 1
                    self.special_map[new_name] = new_key[0]

        self.IRCServerModule = NewIRCServerModule

        
        ######################################################################
        # Server options
        self.server_op = OptionParser(
            version="0.1a",
            description="CPSC 3600 IRC Server application")
        self.server_op.add_option(
            "--servername",
            metavar="X", type="string",
            help="The name for this server")
        self.server_op.add_option(
            "--port",
            metavar="X", type="int",
            help="The port this server listens on")
        self.server_op.add_option(
            "--info",
            metavar="X", type="string",
            help="Human readable information about this server")
        self.server_op.add_option(
            "--connect_to_host",
            metavar="X", type="string",
            help="Connect to a server running on this host")  
        self.server_op.add_option(
            "--connect_to_port",
            metavar="X", type="int",
            help="Connect to a server running on port X")  
        self.server_op.add_option(
            "--debug",
            action="store_true",
            help="print debug messages to stdout")
        self.server_op.add_option(
            "--verbose",
            action="store_true",
            help="be verbose (print some progress messages to stdout)")
        self.server_op.add_option(
            "--log-file",
            metavar="X",
            help="store log in file X")

        ######################################################################
        # Server options
        self.message_op = OptionParser(
            version="0.1a",
            description="CPSC 3600 IRC Server application")
        self.message_op.add_option(
            "--source",
            metavar="X", type="string",
            help="The name for this server")
        self.message_op.add_option(
            "--destination",
            metavar="X", type="string",
            help="The port this server listens on")
        self.message_op.add_option(
            "--message",
            metavar="X", type="string",
            help="Human readable information about this server")


        ######################################################################
        # The mapping between commands and functions
        self.command_handlers = {
            # Connection Registration message handlers
            "LAUNCHSERVER":self.launch_server,
            "SEND":self.send_message,
            "WAIT":self.wait,
            "KILL":self.kill,
        }

        # If we have any overwrite methods, then overwrite those methods
        # if overwrite_methods:
        #     for method in overwrite_methods:
        #         setattr(server, method, lambda: eval(overwrite_methods[method]))
        pass


    def run_test(self, test):
        try :
            self.threads = {}
            self.servers = {}
            self.clients = {}

            # Loop through all of the commands in this test
            for command in test['commands']:
                # Parse out the first command, which dictates what happens on this row
                instructions = command.split(" ", 1)

                # Execute the appropriate command
                result = self.command_handlers[instructions[0]](instructions[1])

                # Store the resulting object (server or client), if returned
                if type(result) is self.IRCServerModule:
                    self.servers[result.servername] = result
                
            # Wait until all of the threads have finished running
            for x in self.threads.values():
                x['thread'].join()

            return self.check_test_results(test, self.servers, self.clients)

        except Exception as e:
            for x in self.threads.values():
                x['app'].request_terminate = True
            for x in self.threads.values():
                x['thread'].join()
            return False, e


    ######################################################################
    def launch_servers(self, config):
        servers = {}

        # Loop through all of the commands in this test
        for command in config['commands']:
            # Parse out the first command, which dictates what happens on this row
            instructions = command.split(" ", 1)

            # Execute the appropriate command
            result = self.launch_server(instructions[1])

            servers[result.servername] = result

        return servers


    ######################################################################
    def launch_server(self, args):
        print("\nStarting " + args)
        # https://stackoverflow.com/questions/16710076/python-split-a-string-respect-and-preserve-quotes
        args = re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', args)
        options, unknownargs = self.server_op.parse_args(args)
        server = self.IRCServerModule(options, run_on_localhost=True)
        server.unknown_server_additions = unknownargs
        server.unknown_server_additions_idx = 0

        # # Override the process data method
        # setattr(server, "process_data", self.new_process_data)

        # # Add the method write data
        # setattr(server, "write_data", self.new_write_data)

        x = threading.Thread(target=server.run)
        self.threads[server.servername] = {
            'thread':x,
            'app':server
        }
        x.start()
        return server


    ######################################################################
    def send_message(self, args):
        print("\nRunning client command: " + args)
        # https://stackoverflow.com/questions/16710076/python-split-a-string-respect-and-preserve-quotes
        args = re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', args)
        options, args = self.message_op.parse_args(args)

        source = self.servers[options.source]
        desintation = options.destination
        message = options.message

        source.write_data(desintation, message)


    ######################################################################
    # One arg: time to wait
    def wait(self, args):
        print("Waiting... %s" % args)
        time.sleep(float(args))

    ######################################################################
    # One arg: what to kill
    # - ALL --> kill everything
    # - name --> kill a server or a client
    def kill(self, args):
        if args == "ALL":
            for irc in self.threads.values():
                irc['app'].request_terminate = True 
                irc['thread'].join()
        elif args in self.threads:
            self.threads[args]['app'].request_terminate = True
            self.threads[args]['thread'].join()
        else:
            # Bad name for a thread to kill...
            pass


    def check_test_results(self, test, servers, clients):        
        problems = ""

        for state in test['final_state']:
            if state in servers:
                r, p = self.check_server(servers[state], test['final_state'][state])
                if not r:
                    problems += p

        # If there were problems, then this test fails and we return them
        if problems:
            return False, problems
        else:
            return True, None


    def check_server(self, server, configuration):
        problems = ""

        if 'sent_messages_asdqw' in configuration:
            problems += self.find_problems_with_server(server.servername, "sent_messages_asdqw", server.sent_messages_asdqw, configuration['sent_messages_asdqw'])
        if 'recvd_messages_asdqw' in configuration:
            problems += self.find_problems_with_server(server.servername, "recvd_messages_asdqw", server.recvd_messages_asdqw, configuration['recvd_messages_asdqw'])
        
        if problems:
            return False, problems
        else:
            return True, None


    def find_problems_with_server(self, servername, propertyname, server_list, configuration_list):
        problems = ""
        if len(server_list) != len(configuration_list):
            problems += "%s: Wrong number of %s (found %i, expected %i)\n" % (servername, propertyname, len(server_list), len(configuration_list))
        
        missing_from_server = self.diff(configuration_list, server_list)
        if missing_from_server:
            problems += "%s: Missing from %s: %s\n" % (servername, propertyname, ", ".join(missing_from_server))

        extra_in_server = self.diff(server_list, configuration_list)
        if extra_in_server:
            problems += "%s: Extra in %s: %s\n" % (servername, propertyname, ", ".join(extra_in_server))

        return problems

    # Helper function to find what differences exist in two lists
    def diff(self, list1, list2):
        return (list(set(list1) - set(list2)))

    def union(self, lst1, lst2): 
        final_list = list(set(lst1) | set(lst2)) 
        return final_list

    def intersect(self, lst1, lst2): 
        final_list = list(set(lst1) & set(lst2)) 
        return final_list