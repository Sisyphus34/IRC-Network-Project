import threading
import os
import re
import time
import sys
import json
from optparse import OptionParser
from IRCServer import IRCServer as IRCServer
from IRCClient import IRCClient
from IRCBasicConnectivityTest import IRCBasicConnectivityTest


class IRCTestManager(object):

    ######################################################################
    # Initialization
    def __init__(self):

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
        # Client options
        self.client_op = OptionParser(
            version="0.1a",
            description="CPSC 3600 IRC Client application")
        self.client_op.add_option(
            "-S", "--serverhost",
            metavar="X",
            help="The name of the server to connect this client to")
        self.client_op.add_option(
            "-P", "--serverport",
            metavar="X",
            help="The port to connect to on the server")
        self.client_op.add_option(
            "-N", "--nick",
            metavar="X",
            help="The requested nickname for this client")
        self.client_op.add_option(
            "--hostname",
            metavar="X",
            help="The name of the machine this client is running on")
        self.client_op.add_option(
            "--realname",
            metavar="X",
            help="The real name of this user")
        self.client_op.add_option(
            "--simulate",
            action="store_true",
            help="Don't request input from a user, but instead loop waiting for commands to send")
        self.client_op.add_option(
            "--verbose",
            action="store_true",
            help="be verbose (print some progress messages to stdout)")
        self.client_op.add_option(
            "--debug",
            action="store_true",
            help="print debug messages to stdout")
        self.client_op.add_option(
            "--log-file",
            metavar="X",
            help="store log in file X")

        ######################################################################
        # Client command options
        self.client_command = OptionParser(
            version="0.1a",
            description="CPSC 3600 IRC Client application")
        self.client_command.add_option(
            "--nick",
            metavar="X",
            help="The name the client who is executing this command")
        self.client_command.add_option(
            "--command",
            metavar="X",
            help="The command to execute")
        self.client_command.add_option(
            "--args",
            nargs='*',
            help="The arguments to pass to the command")

        ######################################################################
        # The mapping between commands and functions
        self.command_handlers = {
            # Connection Registration message handlers
            "LAUNCHSERVER": self.launch_server,
            "LAUNCHCLIENT": self.launch_client,
            "CLIENTCOMMAND": self.run_client_command,
            "WAIT": self.wait,
            "KILL": self.kill,
        }

    ######################################################################
    # Test Management

    def run_tests(self, tests):
        __location__ = os.path.realpath(os.path.join(
            os.getcwd(), os.path.dirname(__file__)))
        if not os.path.exists(os.path.join(__location__, 'Logs')):
            os.makedirs(os.path.join(__location__, 'Logs'))

        score = 0
        results = []
        for test in tests:
            # Open the test file
            with open(os.path.join(__location__, 'TestCases', '%s.cfg' % test), 'r') as fp:
                test_config = json.load(fp)
                # Redirect all output to a log file for this test
                with open(os.path.join(__location__, 'Logs', '%s.log' % test), 'w') as log:
                    sys.stdout = log
                    passed, exception = self.run_test(test_config)
                    results.append({
                        'test': test,
                        'passed': passed,
                        'exception': exception
                    })
                    if passed:
                        score += tests[test]
                    sys.stdout = sys.__stdout__
                    print("%s passed: %r" % (test, passed))
                    if exception:
                        print("%s" % exception)

        return score

    def run_test(self, test):
        if "type" in test:
            if test["type"] == "basic_connectivity":
                tester = IRCBasicConnectivityTest(IRCServer)
                return tester.run_test(test)
        else:
            return self.run_IRC_test(test)

    def run_IRC_test(self, test):
        try:
            self.threads = {}
            self.servers = {}
            self.clients = {}

            # Loop through all of the commands in this test
            for command in test['commands']:
                # Parse out the first command, which dictates what happens on this row
                instructions = command.split(" ", 1)

                # Execute the appropriate command
                result = self.command_handlers[instructions[0]](
                    instructions[1])

                # Store the resulting object (server or client), if returned
                if type(result) is IRCServer:
                    self.servers[result.servername] = result
                elif type(result) is IRCClient:
                    self.clients[result.nick] = result

            # Wait until all of the threads have finished running
            for x in self.threads.values():
                x['thread'].join()

            return self.check_IRC_test_results(test, self.servers, self.clients)

        except Exception as e:
            for x in self.threads.values():
                x['app'].request_terminate = True
            for x in self.threads.values():
                x['thread'].join()
            return False, e

    ######################################################################
    # Verify if test succeeded
    def check_IRC_test_results(self, test, servers, clients):
        problems = ""

        for state in test['final_state']:
            if state in servers:
                r, p = self.check_server(
                    servers[state], test['final_state'][state])
                if not r:
                    problems += p

            elif state in clients:
                pass
                r, p = self.check_client(
                    clients[state], test['final_state'][state])
                if not r:
                    problems += p

        # If there were problems, then this test fails and we return them
        if problems:
            return False, problems
        else:
            return True, None

    def check_server(self, server, configuration):
        problems = ""

        if 'adjacent_users' in configuration:
            problems += self.find_problems_with_server(
                server.servername, "adjacent_users", server.adjacent_users, configuration['adjacent_users'])
        if 'users_lookuptable' in configuration:
            problems += self.find_problems_with_server(
                server.servername, "users_lookuptable", server.users_lookuptable, configuration['users_lookuptable'])
        if 'adjacent_servers' in configuration:
            problems += self.find_problems_with_server(
                server.servername, "adjacent_servers", server.adjacent_servers, configuration['adjacent_servers'])
        if 'servers_lookuptable' in configuration:
            problems += self.find_problems_with_server(
                server.servername, "servers_lookuptable", server.servers_lookuptable, configuration['servers_lookuptable'])
        if 'channels' in configuration:
            problems += self.find_problems_with_server_channels(
                server.servername, configuration['channels'])

        if problems:
            return False, problems
        else:
            return True, None

    def find_problems_with_server(self, servername, propertyname, server_list, configuration_list):
        problems = ""
        if len(server_list) != len(configuration_list):
            problems += "%s: Wrong number of %s (found %i, expected %i)\n" % (
                servername, propertyname, len(server_list), len(configuration_list))

        missing_from_server = self.diff(configuration_list, server_list)
        if missing_from_server:
            problems += "%s: Missing from %s: %s\n" % (
                servername, propertyname, ", ".join(missing_from_server))

        extra_in_server = self.diff(server_list, configuration_list)
        if extra_in_server:
            problems += "%s: Extra in %s: %s\n" % (
                servername, propertyname, ", ".join(extra_in_server))

        return problems

    def find_problems_with_server_channels(self, servername, channels):
        problems = ""

        missing_from_server = self.diff(
            channels, self.servers[servername].channels.keys())
        if missing_from_server:
            problems += "%s: Missing from channels: %s\n" % (
                servername, ", ".join(missing_from_server))

        extra_in_server = self.diff(
            self.servers[servername].channels.keys(), channels)
        if extra_in_server:
            problems += "%s: Extra in channels: %s\n" % (
                servername, ", ".join(extra_in_server))

        for channel in channels:
            problems += self.find_problems_with_server_channel(
                servername, channel, channels[channel])
        return problems

    def find_problems_with_server_channel(self, servername, channel_name, channel_data):
        problems = ""
        if channel_name in self.servers[servername].channels:
            server_channel = self.servers[servername].channels[channel_name]

            if server_channel.key != channel_data['key']:
                problems += "%s: Wrong key in channel %s (found %s, expected %s)\n" % (
                    servername, channel_name, server_channel.key, channel_data['key'])

            if server_channel.topic != channel_data['topic']:
                problems += "%s: Wrong topic in channel %s (found %s, expected %s)\n" % (
                    servername, channel_name, server_channel.topic, channel_data['topic'])

            if len(server_channel.users) != len(channel_data['users']):
                problems += "%s: Wrong number of users in channel %s (found %i, expected %i)\n" % (
                    servername, channel_name, len(server_channel.users), len(channel_data['users']))

            missing_from_server = self.diff(
                channel_data['users'], server_channel.users)
            if missing_from_server:
                problems += "%s: Missing users in channel %s: %s\n" % (
                    servername, channel_name, ", ".join(missing_from_server))

            extra_in_server = self.diff(
                server_channel.users, channel_data['users'])
            if extra_in_server:
                problems += "%s: Extra users in channel %s: %s\n" % (
                    servername, channel_name, ", ".join(extra_in_server))

        return problems

    def check_client(self, client, configuration):
        problems = ""

        # Find any missing, or extra channels
        missing_from_client = self.diff(
            configuration['channels'], client.channels)
        if missing_from_client:
            problems += "%s: Missing channels: %s\n" % (
                client.nick, ", ".join(missing_from_client))

        extra_in_client = self.diff(client.channels, configuration['channels'])
        if extra_in_client:
            problems += "%s: Extra channels: %s\n" % (
                client.nick, ", ".join(extra_in_client))

        # Search for problems in any of the channels present
        # Only consider channels that are present in BOTH lists
        for channelname in self.intersect(client.channels.keys(), configuration["channels"].keys()):
            problems += self.find_problems_with_client_channel(
                client.nick, channelname, client.channels[channelname], configuration["channels"][channelname])

        # Check for issues in the printed messages
        missing_from_client = self.diff(
            configuration['printed_messages'], client.printed_messages)
        if missing_from_client:
            problems += "%s: Missing messages: %s\n" % (
                client.nick, ", ".join(missing_from_client))

        extra_in_client = self.diff(
            client.printed_messages, configuration['printed_messages'])
        if extra_in_client:
            problems += "%s: Extra messages: %s\n" % (
                client.nick, ", ".join(extra_in_client))

        if problems:
            return False, problems
        else:
            return True, None

    def find_problems_with_client_channel(self, nick, channelname, channel, configuration):
        problems = ""

        # Check for issues in the users noted in this channel
        missing_from_channel = self.diff(configuration['users'], channel.users)
        if missing_from_channel:
            problems += "%s: Missing users in %s: %s\n" % (
                nick, channelname, ", ".join(missing_from_channel))

        extra_in_channel = self.diff(channel.users, configuration['users'])
        if extra_in_channel:
            problems += "%s: Extra users in %s: %s\n" % (
                nick, channelname, ", ".join(extra_in_channel))

        if channel.topic != configuration['topic']:
            problems += "%s: Wrong topic in channel %s (found %s, expected %s)\n" % (
                nick, channelname, channel.topic, configuration['topic'])

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

    ######################################################################
    ######################################################################
    # The following functions are command handlers

    ######################################################################

    def launch_server(self, args):
        print("\nStarting " + args)
        # https://stackoverflow.com/questions/16710076/python-split-a-string-respect-and-preserve-quotes
        args = re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', args)
        options, args = self.server_op.parse_args(args)
        server = IRCServer(options, run_on_localhost=True)

        x = threading.Thread(target=server.run)
        self.threads[server.servername] = {
            'thread': x,
            'app': server
        }
        x.start()
        return server

    ######################################################################

    def launch_client(self, args):
        print("\nStarting " + args)
        # https://stackoverflow.com/questions/16710076/python-split-a-string-respect-and-preserve-quotes
        args = re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', args)
        options, args = self.client_op.parse_args(args)
        client = IRCClient(options, run_on_localhost=True)

        x = threading.Thread(target=client.run)
        self.threads[client.nick + "@" + client.servername] = {
            'thread': x,
            'app': client
        }
        x.start()
        return client

    ######################################################################

    def run_client_command(self, args):
        print("\nRunning client command: " + args)
        # https://stackoverflow.com/questions/16710076/python-split-a-string-respect-and-preserve-quotes
        args = re.findall(r'(?:[^\s,"]|"(?:\\.|[^"])*")+', args)
        options, args = self.client_command.parse_args(args)

        client = self.clients[options.nick]
        if options.command == "QUIT":
            if len(args) > 0:
                client.quit(args[0])
            else:
                client.quit()

        elif options.command == "JOIN":
            # Join without a password
            if len(args) == 1:
                client.join(args[0])
            # Join with a password
            elif len(args) == 2:
                client.join(args[0], args[1])

        elif options.command == "PART":
            client.part(args[0])

        elif options.command == "TOPIC":
            # Request the topic
            if len(args) == 1:
                client.topic(args[0])
            # Change the topic
            elif len(args) == 2:
                client.topic(args[0], args[1])

        elif options.command == "NAMES":
            # Request all names
            if len(args) == 0:
                client.names()
            # Request the names in a specific channel
            elif len(args) == 1:
                client.names(args[0])

        elif options.command == "LIST":
            # Request all names
            if len(args) == 0:
                client.list()
            # Request the names in a specific channel
            elif len(args) == 1:
                client.list(args[0])

        elif options.command == "PRIVMSG":
            client.privmsg(args[0], args[1])

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


if __name__ == "__main__":

    test_manager = IRCTestManager()
    basic_score = 0
    IRC_connection_score = 0
    IRC_channel_score = 0
    IRC_messaging_score = 0

    # These public test cases are worth 50 points. When grading your project, we will also run
    # hidden test cases that are worth 25 points. These test cases cover the same functionality, so
    # if your code is correct and passes the public test cases, it SHOULD also pass the
    # hidden test cases. Your grade on the project will be equal to your score on the
    # public test cases + your score on the hidden test cases. The highest possible score is 75 points
    basic_connection_tests = {
        'BasicConnectivity_1_TwoServers': 5,
        'BasicConnectivity_2_FourServers': 5,
    }
    basic_score = test_manager.run_tests(basic_connection_tests)

    IRC_connection_tests = {
        # 12 points
        'ServerConnections_1_TwoServers': 3,
        'ServerConnections_2_FourServers': 4,
        'ServerConnections_3_EightServers': 5,

        # 9 points
        'ClientServerConnections_1_OneServer_OneClient':1,
        'ClientServerConnections_2_OneServer_FourClients':3,
        'ClientServerConnections_3_ThreeServers_SevenClients':4,
        'ClientServerConnections_4_ERROR_NickCollision':1,

        # 3 points
        'QUIT_1_OneServer_FourClient':1,
        'QUIT_2_ThreeServers_SevenClients':2,
    }
    IRC_connection_score = test_manager.run_tests(IRC_connection_tests)

    IRC_channel_tests = {
        # # 6 points
        # 'JOIN_1_OneClient_OneChannel':0.5,
        # 'JOIN_2_OneClient_OneChannel_WithKey':0.5,
        # 'JOIN_3_ERROR_BadKey':0.5,
        # 'JOIN_4_ThreeServers_SevenClients_TwoChannels':1,
        # 'JOIN_5_ThreeServers_SevenClients_TwoChannels_WithKey':1,
        # 'JOIN_QUIT_6_ThreeServers_SevenClients_TwoChannels':2.5,

        # # 4 points
        # 'PART_1_OneClient_OneChannel':1,
        # 'PART_2_ERROR_NoSuchChannel':0.5,
        # 'PART_3_ERROR_NotOnChannel':0.5,
        # 'PART_4_ThreeServers_SevenClients_TwoChannels':2,

        # # 4 points
        # 'TOPIC_1_OneClient_OneChannel':0.5,
        # 'TOPIC_2_ERROR_NoSuchChannel':0.5,
        # 'TOPIC_3_ERROR_NotOnChannel':0.5,
        # 'TOPIC_4_ThreeServers_SevenClients_TwoChannels':0.5,
        # 'TOPIC_5_ServerCreatedAfterChannel':2,

        # # 2 points
        # 'NAMES_1_OneClient_OneChannel':0.5,
        # 'NAMES_2_ERROR_NoSuchChannel':0.5,
        # 'NAMES_3_ThreeServers_SevenClients_TwoChannels':1,
    }
    IRC_channel_score = test_manager.run_tests(IRC_channel_tests)

    IRC_messaging_tests = {
        # # 10 points
        # 'PRIVMSG_1_OneMessage_ToUser':0.5,
        # 'PRIVMSG_2_ERROR_NoSuchNick':0.5,
        # 'PRIVMSG_3_OneMessage_ToChannel':1,
        # 'PRIVMSG_4_ERROR_NoSuchChannel':0.5,
        # 'PRIVMSG_5_ERROR_NotOnChannel':0.5,
        # 'PRIVMSG_6_MultipleMessages_ToUsers':2,
        # 'PRIVMSG_7_MultipleMessages_ToChannels':2,
        # 'PRIVMSG_8_MultipleMessages_ToUsersAndChannels':3,
    }
    IRC_messaging_score = test_manager.run_tests(IRC_channel_tests)

    print("#############################")
    print("Points scored on basic test cases: %s/10" % basic_score)
    print("Points scored on IRC connection test cases: %s/24" %
          IRC_connection_score)
    print("Points scored on IRC channel test cases: %s/16" % IRC_channel_score)
    print("Points scored on IRC messaging test cases: %s/10" %
          IRC_messaging_score)
