import test
from connections import ContrailConnections
from common import isolated_creds
from random import randint

import os
import unittest
import fixtures
import testtools
import traceback
import signal
import traffic_tests
from contrail_test_init import *
from vn_test import *
from quantum_test import *
from vnc_api_test import *
from nova_test import *
from vm_test import *
from connections import ContrailConnections
from floating_ip import *
from control_node import *
from policy_test import *
from multiple_vn_vm_test import *
from vdns_fixture import *
from contrail_fixtures import *
from vnc_api import vnc_api
from vnc_api.gen.resource_test import *
from tcutils.wrappers import preposttest_wrapper

class BasevDNSTest(test.BaseTestCase):

    @classmethod
    def setUpClass(cls):
        super(BasevDNSTest, cls).setUpClass()
        cls.isolated_creds = isolated_creds.IsolatedCreds(cls.__name__, \
				cls.inputs, ini_file = cls.ini_file, \
				logger = cls.logger)
        cls.isolated_creds.setUp()
        cls.project = cls.isolated_creds.create_tenant() 
        cls.isolated_creds.create_and_attach_user_to_tenant()
        cls.inputs = cls.isolated_creds.get_inputs()
        cls.connections = cls.isolated_creds.get_conections() 
        cls.quantum_fixture= cls.connections.quantum_fixture
        cls.nova_fixture = cls.connections.nova_fixture
        cls.vnc_lib= cls.connections.vnc_lib
        cls.agent_inspect= cls.connections.agent_inspect
        cls.cn_inspect= cls.connections.cn_inspect
        cls.analytics_obj=cls.connections.analytics_obj
        cls.dnsagent_inspect = cls.connections.dnsagent_inspect
        cls.api_s_inspect = cls.connections.api_server_inspect
    #end setUpClass

    @classmethod
    def tearDownClass(cls):
        #cls.isolated_creds.delete_user()
        cls.isolated_creds.delete_tenant()
        super(BasevDNSTest, cls).tearDownClass()
    #end tearDownClass 

    def verify_dns_record_order(self, record_order, test_type='test_record_order', record_num=10):
        ''' This test tests DNS record order.
            Round-Robin/Fixed/Random
        '''
        random_number = randint(2500,5000)
        vn1_ip = '10.10.10.1'
        vn_name = 'vn' + str(random_number)
        dns_server_name = 'vdns1' + str(random_number)
        domain_name = 'juniper.net'
        ttl = 100
        ipam_name = 'ipam1' + str(random_number)
        project_fixture = self.useFixture(ProjectFixture(
            vnc_lib_h=self.vnc_lib, project_name=self.inputs.project_name, connections=self.connections))
        proj_fixt = self.useFixture(
            ProjectTestFixtureGen(self.vnc_lib, project_name=self.inputs.project_name))
        dns_data = VirtualDnsType(
            domain_name=domain_name, dynamic_records_from_client=True,
            default_ttl_seconds=ttl, record_order=record_order)
        # Create VDNS server object.
        vdns_fixt1 = self.useFixture(VdnsFixture(
            self.inputs, self.connections, vdns_name=dns_server_name, dns_data=dns_data))
        result, msg = vdns_fixt1.verify_on_setup()
        self.assertTrue(result, msg)
        dns_server = IpamDnsAddressType(
            virtual_dns_server_name=vdns_fixt1.vdns_fq_name)
        ipam_mgmt_obj = IpamType(
            ipam_dns_method='virtual-dns-server', ipam_dns_server=dns_server)
        # Associate VDNS with IPAM.
        ipam_fixt1 = self.useFixture(NetworkIpamTestFixtureGen(self.vnc_lib, virtual_DNS_refs=[
                                     vdns_fixt1.obj], parent_fixt=proj_fixt, network_ipam_name=ipam_name, network_ipam_mgmt=ipam_mgmt_obj))
        vn_nets = {
            vn_name : [(ipam_fixt1.getObj(), VnSubnetsType([IpamSubnetType(subnet=SubnetType(vn1_ip, 24))]))],
        }
        # Launch VN with IPAM
        vn_fixt = self.useFixture(
            VirtualNetworkTestFixtureGen(
                self.vnc_lib, virtual_network_name=vn_name,
                network_ipam_ref_infos=vn_nets[vn_name], parent_fixt=proj_fixt, id_perms=IdPermsType(enable=True)))
        vn_quantum_obj = self.quantum_fixture.get_vn_obj_if_present(
            vn_name=vn_fixt._name, project_id=proj_fixt._obj._uuid)
        vm_fixture = self.useFixture(
            VMFixture(project_name=self.inputs.project_name,
                      connections=self.connections, vn_obj=vn_quantum_obj, vm_name='vm1-test'))
        vm_fixture.verify_vm_launched()
        vm_fixture.verify_on_setup()
        vm_fixture.wait_till_vm_is_up()

        rec_ip_list = []
        i = 1
        j = 1
        k = 1
        l = 1
        verify_rec_name_list = []
        verify_rec_name_ip = {}
        if test_type == 'recordscaling':
            self.logger.info('Creating %s number of records', record_num)
            for num in range(1, record_num):
                rec = 'test-rec-' + str(j) + '-' + str(i) + str(random_number)
                self.logger.info('Creating record %s', rec)
                recname = 'rec' + str(j) + '-' + str(i) + str(random_number)
                rec_ip = str(l) + '.' + str(k) + '.' + str(j) + '.' + str(i)
                vdns_rec_data = VirtualDnsRecordType(
                    recname, 'A', 'IN', rec_ip, ttl)
                vdns_rec_fix = self.useFixture(VdnsRecordFixture(
                    self.inputs, self.connections, rec, vdns_fixt1.vdns_fix, vdns_rec_data))
                sleep(1)
                i = i + 1
                if i > 253:
                    j = j + 1
                    i = 1
                if j > 253:
                    k = k + 1
                    j = 1
                    i = 1
                # sleep for some time after configuring 10 records.
                if num % 10 == 0:
                    sleep(0.5)
                # pic some random records for nslookup verification
                if num % 100 == 0:
                    verify_rec_name_list.append(recname)
                    verify_rec_name_ip[recname] = rec_ip
            # Sleep for some time - DNS takes some time to sync with BIND
            # server
            self.logger.info(
                'Sleep for 180sec to sync vdns server with vdns record entry')
            sleep(180)
            # Verify NS look up works for some random records values
            self.logger.info('****NSLook up verification****')
            import re
            for rec in verify_rec_name_list:
                cmd = 'nslookup ' + rec
                vm_fixture.run_cmd_on_vm(cmds=[cmd])
                result = vm_fixture.return_output_cmd_dict[cmd]
                result = result.replace("\r", "")
                result = result.replace("\t", "")
                result = result.replace("\n", " ")
                m_obj = re.search(
                    r"Address:[0-9.]*#[0-9]*\s*.*Name:(.*\.juniper\.net)\s*Address:\s*([0-9.]*)", result)
                if not m_obj:
                    #import pdb; pdb.set_trace()
                    self.assertTrue(
                        False, 'record search is failed,please check syntax of the regular expression/NSlookup is failed')
                print ('vm_name is ---> %s \t ip-address is ---> %s' %
                       (m_obj.group(1), m_obj.group(2)))
        else:
            for num in range(1, record_num):
                rec = 'test-rec-' + str(j) + '-' + str(i) + str(random_number)
                rec_ip = '1.' + '1.' + str(j) + '.' + str(i)
                vdns_rec_data = VirtualDnsRecordType(
                    'test1', 'A', 'IN', rec_ip, ttl)
                vdns_rec_fix = self.useFixture(VdnsRecordFixture(
                    self.inputs, self.connections, rec, vdns_fixt1.vdns_fix, vdns_rec_data))
                result, msg = vdns_rec_fix.verify_on_setup()
                i = i + 1
                if i > 253:
                    j = j + 1
                    i = 1
                rec_ip_list.append(rec_ip)
                sleep(2)
            # Get the NS look up record Verify record order
            cmd = 'nslookup test1'
            vm_fixture.run_cmd_on_vm(cmds=[cmd])
            result = vm_fixture.return_output_cmd_dict[cmd]
            result = result.replace("\r", "")
            result = result.replace("\t", "")
            result = result.replace("\n", " ")
            import re
            m_obj = re.search(
                r"Address:[0-9.]*#[0-9]*\s*Name:test1.juniper.net\s*(Address:\s*[0-9.]*)", result)
            if not m_obj:
                self.assertTrue(
                    False, 'record search is failed,please check syntax of regular expression')
            print m_obj.group(1)
            dns_record = m_obj.group(1).split(':')
            dns_record_ip = dns_record[1].lstrip()
            next_ip = self.next_ip_in_list(rec_ip_list, dns_record_ip)
            for rec in rec_ip_list:
                vm_fixture.run_cmd_on_vm(cmds=[cmd])
                result = vm_fixture.return_output_cmd_dict[cmd]
                result = result.replace("\r", "")
                result = result.replace("\t", "")
                result = result.replace("\n", " ")
                m_obj = re.search(
                    r"Address:[0-9.]*#[0-9]*\s*Name:test1.juniper.net\s*(Address:\s*[0-9.]*)", result)
                print m_obj.group(1)
                dns_record = m_obj.group(1).split(':')
                dns_record_ip1 = dns_record[1].lstrip()
                if record_order == 'round-robin':
                    if next_ip != dns_record_ip1:
                        print "\n VDNS records are not sent in round-robin order"
                        self.assertTrue(
                            False, 'VDNS records are not sent in round-robin order')
                    next_ip = self.next_ip_in_list(rec_ip_list, dns_record_ip1)
                if record_order == 'random':
                    if dns_record_ip1 not in rec_ip_list:
                        print "\n VDNS records are not sent in random order"
                        self.assertTrue(
                            False, 'VDNS records are not sent random order')
                if record_order == 'fixed':
                    if dns_record_ip != dns_record_ip1:
                        print "\n VDNS records are not sent fixed in fixed order"
                        self.assertTrue(
                            False, 'VDNS records are not sent fixed in fixed order')
        return True
    # end test_dns_record_order
    # This Test test vdns functionality with control node restart
    def vdns_with_cn_dns_agent_restart(self, restart_process):
        '''
         This test test the functionality of controlnode/dns/agent restart with vdns feature.
        '''
        if restart_process == 'ControlNodeRestart':
            if len(set(self.inputs.bgp_ips)) < 2:
                raise self.skipTest(
                    "Skiping Test. At least 2 control nodes required to run the control node switchover test")
        vn1_ip = '10.10.10.1'
        vm_list = ['vm1-test', 'vm2-test']
        vn_name = 'vn1'
        dns_server_name = 'vdns1'
        domain_name = 'juniper.net'
        ttl = 100
        ipam_name = 'ipam1'
        rev_zone = vn1_ip.split('.')
        rev_zone = '.'.join((rev_zone[0], rev_zone[1], rev_zone[2]))
        rev_zone = rev_zone + '.in-addr.arpa'
        project_fixture = self.useFixture(ProjectFixture(
            vnc_lib_h=self.vnc_lib, project_name=self.inputs.project_name, connections=self.connections))
        proj_fixt = self.useFixture(
            ProjectTestFixtureGen(self.vnc_lib, project_name=self.inputs.project_name))
        dns_data = VirtualDnsType(
            domain_name=domain_name, dynamic_records_from_client=True,
            default_ttl_seconds=ttl, record_order='random')
        # Create VDNS server object.
        vdns_fixt1 = self.useFixture(VdnsFixture(
            self.inputs, self.connections, vdns_name=dns_server_name, dns_data=dns_data))
        result, msg = vdns_fixt1.verify_on_setup()
        self.assertTrue(result, msg)
        dns_server = IpamDnsAddressType(
            virtual_dns_server_name=vdns_fixt1.vdns_fq_name)
        ipam_mgmt_obj = IpamType(
            ipam_dns_method='virtual-dns-server', ipam_dns_server=dns_server)
        # Associate VDNS with IPAM.
        ipam_fixt1 = self.useFixture(NetworkIpamTestFixtureGen(self.vnc_lib, virtual_DNS_refs=[
                                     vdns_fixt1.obj], parent_fixt=proj_fixt, network_ipam_name=ipam_name, network_ipam_mgmt=ipam_mgmt_obj))
        vn_nets = {
            'vn1': [(ipam_fixt1.getObj(), VnSubnetsType([IpamSubnetType(subnet=SubnetType(vn1_ip, 24))]))],
        }
        # Launch VN with IPAM
        vn_fixt = self.useFixture(
            VirtualNetworkTestFixtureGen(
                self.vnc_lib, virtual_network_name=vn_name,
                network_ipam_ref_infos=vn_nets[vn_name], parent_fixt=proj_fixt, id_perms=IdPermsType(enable=True)))
        vm_fixture = {}
        vm_dns_exp_data = {}
        # Launch  VM with VN Created above. This test verifies on launch of VM agent should updated DNS 'A' and 'PTR' records
        # The following code will verify the same. Also, we should be able ping
        # with VM name.
        for vm_name in vm_list:
            vn_quantum_obj = self.quantum_fixture.get_vn_obj_if_present(
                vn_name=vn_fixt._name, project_id=proj_fixt._obj._uuid)
            vm_fixture[vm_name] = self.useFixture(
                VMFixture(project_name=self.inputs.project_name, connections=self.connections, vn_obj=vn_quantum_obj, vm_name=vm_name))
            vm_fixture[vm_name].verify_vm_launched()
            vm_fixture[vm_name].verify_on_setup()
            vm_fixture[vm_name].wait_till_vm_is_up()
            vm_ip = vm_fixture[vm_name].get_vm_ip_from_vm(
                vn_fq_name=vm_fixture[vm_name].vn_fq_name)
            vm_rev_ip = vm_ip.split('.')
            vm_rev_ip = '.'.join(
                (vm_rev_ip[3], vm_rev_ip[2], vm_rev_ip[1], vm_rev_ip[0]))
            vm_rev_ip = vm_rev_ip + '.in-addr.arpa'
            # Frame the Expected DNS data for VM, one for 'A' record and
            # another 'PTR' record.
            rec_name = vm_name + "." + domain_name
            vm_dns_exp_data[vm_name] = [{'rec_data': vm_ip, 'rec_type': 'A', 'rec_class': 'IN', 'rec_ttl': str(
                ttl), 'rec_name': rec_name, 'installed': 'yes', 'zone': domain_name}, {'rec_data': rec_name, 'rec_type': 'PTR', 'rec_class': 'IN', 'rec_ttl': str(ttl), 'rec_name': vm_rev_ip, 'installed': 'yes', 'zone': rev_zone}]
            self.verify_vm_dns_data(vm_dns_exp_data[vm_name])
        # ping between two vms which are in same subnets by using name.
        self.assertTrue(vm_fixture['vm1-test']
                        .ping_with_certainty(ip=vm_list[1]))
        active_controller = vm_fixture['vm1-test'].get_active_controller()
        self.logger.info('Active control node from the Agent %s is %s' %
                         (vm_fixture['vm1-test'].vm_node_ip, active_controller))
        # Control node restart/switchover.
        if restart_process == 'ControlNodeRestart':
            # restart the Active control node
            self.logger.info('restarting active control node')
            self.inputs.restart_service(
                'contrail-control', [active_controller])
            sleep(5)
            # Check the control node shifted to other control node
            new_active_controller = vm_fixture[
                'vm1-test'].get_active_controller()
            self.logger.info('Active control node from the Agent %s is %s' %
                             (vm_fixture['vm1-test'].vm_node_ip, new_active_controller))
            if new_active_controller == active_controller:
                self.logger.error(
                    'Control node switchover fail. Old Active controlnode was %s and new active control node is %s' %
                    (active_controller, new_active_controller))
                return False
            self.inputs.restart_service(
                'contrail-control', [new_active_controller])
        if restart_process == 'DnsRestart':
            # restart the dns process in the active control node
            self.logger.info(
                'restart the dns process in the active control node')
            self.inputs.restart_service('contrail-dns', [active_controller])
        if restart_process == 'NamedRestart':
            # restart the named process in the active control node
            self.logger.info(
                'restart the named process in the active control node')
            self.inputs.restart_service('contrail-named', [active_controller])
        # restart the agent process in the compute node
        if restart_process == 'AgentRestart':
            self.logger.info('restart the agent process')
            for compute_ip in self.inputs.compute_ips:
                self.inputs.restart_service('contrail-vrouter', [compute_ip])
        if restart_process == 'scp':
            self.logger.info('scp using name of vm')
            vm_fixture['vm1-test'].put_pub_key_to_vm()
            vm_fixture['vm2-test'].put_pub_key_to_vm()
            size = '1000'
            file = 'testfile'
            y = 'ls -lrt %s' % file
            cmd_to_check_file = [y]
            cmd_to_sync = ['sync']
            create_result = True
            transfer_result = True

            self.logger.info("-" * 80)
            self.logger.info("FILE SIZE = %sB" % size)
            self.logger.info("-" * 80)
            self.logger.info('Creating a file of the specified size on %s' %
                             vm_fixture['vm1-test'].vm_name)

            self.logger.info('Transferring the file from %s to %s using scp' %
                             (vm_fixture['vm1-test'].vm_name, vm_fixture['vm2-test'].vm_name))
            vm_fixture[
                'vm1-test'].check_file_transfer(dest_vm_fixture=vm_fixture['vm2-test'], mode='scp', size=size)

            self.logger.info('Checking if the file exists on %s' %
                             vm_fixture['vm2-test'].vm_name)
            vm_fixture['vm2-test'].run_cmd_on_vm(cmds=cmd_to_check_file)
            output = vm_fixture['vm2-test'].return_output_cmd_dict[y]
            print output
            if size in output:
                self.logger.info(
                    'File of size %sB transferred via scp properly' % size)
            else:
                transfer_result = False
                self.logger.error(
                    'File of size %sB not transferred via scp ' % size)
            assert transfer_result, 'File not transferred via scp'
        # Verify after controlnode/dns/agent/named process restart ping vm's by
        # using name.
        for vm_name in vm_list:
            msg = "Ping by using name %s is failed after controlnode/dns/agent/named process restart. Dns server should resolve VM name to IP" % (
                vm_name)
            self.assertTrue(vm_fixture[vm_name]
                            .ping_with_certainty(ip=vm_name), msg)
            self.verify_vm_dns_data(vm_dns_exp_data[vm_name])
        return True
    # end test_vdns_controlnode_switchover

    def next_ip_in_list(self, iplist, item):
        item_index = iplist.index(item)
        next_item = None
        # if it not end of list, return next element in the list
        if item_index != (len(iplist) - 1):
            next_item = iplist[item_index + 1]
        # if the item is on end of list, the next element will be first element
        # in the list
        else:
            next_item = iplist[0]
        return next_item

    def verify_ns_lookup_data(self, vm_fix, cmd, expectd_data):
        self.logger.info("Inside verify_ns_lookup_data")
        self.logger.info(
            "cmd string is %s and  expected data %s for searching" %
            (cmd, expectd_data))
        vm_fix.run_cmd_on_vm(cmds=[cmd])
        result = vm_fix.return_output_cmd_dict[cmd]
        print ('\n result %s' % result)
        if (result.find(expectd_data) == -1):
            return False
        return True

    def verify_vm_dns_data(self, vm_dns_exp_data):
        self.logger.info("Inside verify_vm_dns_data")
        result = True
        dnsinspect_h = self.dnsagent_inspect[self.inputs.bgp_ips[0]]
        dns_data = dnsinspect_h.get_dnsa_config()
        vm_dns_act_data = []
        msg = ''

        # Traverse over expected record data
        found_rec = False
        for expected in vm_dns_exp_data:
            # Get te actual record data from introspect
            for act in dns_data:
                for rec in act['records']:
                    if rec['rec_name'] in expected['rec_name']:
                        vm_dns_act_data = rec
                        found_rec = True
                        break
                if found_rec:
                    break
            if not vm_dns_act_data:
                self.logger.info("DNS record match not found in dns agent")
                return False
            found_rec = False
            # Compare the DNS entries populated dynamically on VM Creation.
            self.logger.info(
                "actual record data %s ,\n expected record data %s" %
                (vm_dns_act_data, expected))
            if(vm_dns_act_data['rec_name'] not in expected['rec_name']):
                result = result and False
            if (vm_dns_act_data['rec_data'] not in expected['rec_data']):
                msg = 'DNS record data info is not matching\n'
                result = result and False
            if(vm_dns_act_data['rec_type'] != expected['rec_type']):
                msg = msg + 'DNS record_type info is not matching\n'
                result = result and False
            if(vm_dns_act_data['rec_ttl'] != expected['rec_ttl']):
                msg = msg + 'DNS record ttl info is not matching\n'
                result = result and False
            if(vm_dns_act_data['rec_class'] != expected['rec_class']):
                msg = msg + 'DNS record calss info is not matching\n'
                result = result and False
            vm_dns_act_data = []
            self.assertTrue(result, msg)
        self.logger.info("Out of verify_vm_dns_data")
        return True
    # end verify_vm_dns_data
