import unittest
from tcutils.wrappers import preposttest_wrapper
from vnc_api.vnc_api import NoIdError
from verify import VerifySecGroup
from policy_test import PolicyFixture
from vn_test import MultipleVNFixture
from vm_test import MultipleVMFixture
from base import BaseSGTest
from policy.config import ConfigPolicy
from security_group import SecurityGroupFixture
from vn_test import VNFixture
from vm_test import VMFixture
from topo_helper import *
import os
import sys
sys.path.append(os.path.realpath('scripts/flow_tests'))
from sdn_topo_setup import *
import test


class SecurityGroupRegressionTests1(BaseSGTest, VerifySecGroup, ConfigPolicy):

    @classmethod
    def setUpClass(cls):
        super(SecurityGroupRegressionTests1, cls).setUpClass()

    def runTest(self):
        pass

    @test.attr(type=['sanity'])
    @preposttest_wrapper
    def test_sec_group_add_delete(self):
        """Verify security group add delete
            1. Create custom security group with rule in it
            2. Delete custom security group
        Pass criteria: Step 1 and 2 should pass
        """
        rule = [{'direction': '>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 8000, 'end_port': 8000}],
                 'src_ports': [{'start_port': 9000, 'end_port': 9000}],
                 'src_addresses': [{'security_group': 'local'}],
                 }]
        secgrp_fix = self.config_sec_group(name='test_sec_group', entries=rule)
        self.delete_sec_group(secgrp_fix)
        return True

    @test.attr(type=['sanity'])
    @preposttest_wrapper
    def test_vm_with_sec_group(self):
        """Verify attach dettach security group in VM
            1. Create VN with subnet
            2. Create security group with custom rules
            3. Launch VM in custom created security group and verify
            4. Remove secuity group association with VM
            5. Add back custom security group to VM and verify
            6. Try to delete security group with association to VM. It should fail.
        Pass criteria: Step 2,3,4,5 and 6 should pass
        """
        vn_name = "test_sec_vn"
        vn_net = ['11.1.1.0/24']
        vn = self.useFixture(VNFixture(
            project_name=self.inputs.project_name, connections=self.connections,
            vn_name=vn_name, inputs=self.inputs, subnets=vn_net))
        assert vn.verify_on_setup()

        secgrp_name = 'test_sec_group'
        rule = [{'direction': '>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 8000, 'end_port': 8000}],
                 'src_ports': [{'start_port': 9000, 'end_port': 9000}],
                 'src_addresses': [{'security_group': 'local'}],
                 }]
        secgrp = self.config_sec_group(name=secgrp_name, entries=rule)
        secgrp_id = secgrp.secgrp_fix._obj.uuid
        vm_name = "test_sec_vm"
        vm = self.useFixture(VMFixture(
            project_name=self.inputs.project_name, connections=self.connections,
            vn_obj=vn.obj, vm_name=vm_name, image_name='ubuntu-traffic', flavor='contrail_flavor_small',
            sg_ids=[secgrp_id]))
        assert vm.verify_on_setup()
        assert vm.wait_till_vm_is_up()
        result, msg = vm.verify_security_group(secgrp_name)
        assert result, msg

        self.logger.info("Remove security group %s from VM %s",
                         secgrp_name, vm_name)
        vm.remove_security_group(secgrp=secgrp_name)
        result, msg = vm.verify_security_group(secgrp_name)
        if result:
            assert False, "Security group %s is not removed from VM %s" % (secgrp_name,
                                                                           vm_name)

        import time
        time.sleep(4)
        vm.add_security_group(secgrp=secgrp_name)
        result, msg = vm.verify_security_group(secgrp_name)
        assert result, msg

        self.logger.info(
            "Try deleting the security group %s with back ref.", secgrp_name)
        try:
            secgrp.secgrp_fix.cleanUp()
        except Exception, msg:
            self.logger.info(msg)
            self.logger.info(
                "Not able to delete the security group with back ref as expected")
        else:
            try:
                secgroup = self.vnc_lib.security_group_read(
                    fq_name=secgrp.secgrp_fq_name)
                self.logger.info(
                    "Not able to delete the security group with back ref as expected")
            except NoIdError:
                errmsg = "Security group deleted, when it is attached to a VM."
                self.logger.error(errmsg)
                assert False, errmsg

        return True

class SecurityGroupRegressionTests2(BaseSGTest, VerifySecGroup, ConfigPolicy):

    @classmethod
    def setUpClass(cls):
        super(SecurityGroupRegressionTests2, cls).setUpClass()

    def setUp(self):
        super(SecurityGroupRegressionTests2, self).setUp()
	self.create_sg_test_resources()

    def tearDown(self):
        self.logger.debug("Tearing down SecurityGroupRegressionTests2.")
        super(SecurityGroupRegressionTests2, self).tearDown()

    def runTest(self):
        pass

    @preposttest_wrapper
    def test_sec_group_with_proto(self):
        """Verify security group with allow specific protocol on all ports and policy with allow all between VN's"""
        self.logger.info("Configure the policy with allow any")
        rules = [
            {
                'direction': '<>',
                'protocol': 'any',
                'source_network': self.vn1_name,
                'src_ports': [0, -1],
                'dest_network': self.vn2_name,
                'dst_ports': [0, -1],
                'simple_action': 'pass',
            },
        ]
        self.config_policy_and_attach_to_vn(rules)
        rule = [{'direction': '<>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'tcp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg1_fix.replace_rules(rule)

        rule = [{'direction': '<>',
                'protocol': 'udp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'udp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg2_fix.replace_rules(rule)

        self.verify_sec_group_port_proto()
        return True

    @preposttest_wrapper
    def test_sec_group_with_port(self):
        """Verify security group with allow specific protocol/port and policy with allow all between VN's"""
        self.logger.info("Configure the policy with allow any")
        rules = [
            {
                'direction': '<>',
                'protocol': 'any',
                'source_network': self.vn1_name,
                'src_ports': [0, -1],
                'dest_network': self.vn2_name,
                'dst_ports': [0, -1],
                'simple_action': 'pass',
            },
        ]
        self.config_policy_and_attach_to_vn(rules)

        rule = [{'direction': '<>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'src_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'tcp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'dst_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg1_fix.replace_rules(rule)

        rule = [{'direction': '<>',
                'protocol': 'udp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'src_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'udp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'dst_ports': [{'start_port': 8000, 'end_port': 9000}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg2_fix.replace_rules(rule)

        self.verify_sec_group_port_proto(port_test=True)
        return True

#end class SecurityGroupRegressionTests2

class SecurityGroupRegressionTests3(BaseSGTest, VerifySecGroup, ConfigPolicy):

    @classmethod
    def setUpClass(cls):
        super(SecurityGroupRegressionTests3, cls).setUpClass()

    def setUp(self):
        super(SecurityGroupRegressionTests3, self).setUp()
	self.create_sg_test_resources()

    def tearDown(self):
        self.logger.debug("Tearing down SecurityGroupRegressionTests3.")
        super(SecurityGroupRegressionTests3, self).tearDown()

    def runTest(self):
        pass

    @preposttest_wrapper
    def test_sec_group_with_proto_and_policy_to_allow_only_tcp(self):
        """Verify security group with allow specific protocol on all ports and policy with allow only TCP between VN's"""
        self.logger.info("Configure the policy with allow TCP only rule.")
        rules = [
            {
                'direction': '<>',
                'protocol': 'tcp',
                'source_network': self.vn1_name,
                'src_ports': [0, -1],
                'dest_network': self.vn2_name,
                'dst_ports': [0, -1],
                'simple_action': 'pass',
            },
        ]
        self.config_policy_and_attach_to_vn(rules)

        rule = [{'direction': '<>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'tcp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg1_fix.replace_rules(rule)

        rule = [{'direction': '<>',
                'protocol': 'udp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'udp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg2_fix.replace_rules(rule)

        self.verify_sec_group_with_udp_and_policy_with_tcp()
        return True

    @preposttest_wrapper
    def test_sec_group_with_proto_and_policy_to_allow_only_tcp_ports(self):
        """Verify security group with allow specific protocol on all ports and policy with allow only TCP on specifif ports between VN's"""
        self.logger.info(
            "Configure the policy with allow TCP port 8000/9000 only rule.")
        rules = [
            {
                'direction': '<>',
                'protocol': 'tcp',
                'source_network': self.vn1_name,
                'src_ports': [8000, 8000],
                'dest_network': self.vn2_name,
                'dst_ports': [9000, 9000],
                'simple_action': 'pass',
            },
        ]
        self.config_policy_and_attach_to_vn(rules)

        rule = [{'direction': '<>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'tcp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg1_fix.replace_rules(rule)

        rule = [{'direction': '<>',
                'protocol': 'udp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'udp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg2_fix.replace_rules(rule)

        self.verify_sec_group_with_udp_and_policy_with_tcp_port()
        return True

#end class SecurityGroupRegressionTests3

class SecurityGroupRegressionTests4(BaseSGTest, VerifySecGroup, ConfigPolicy):

    @classmethod
    def setUpClass(cls):
        super(SecurityGroupRegressionTests4, cls).setUpClass()

    def runTest(self):
        pass

    @preposttest_wrapper
    def test_SG(self):
        """Tests SG and rules to check if traffic is allowed as per rules in SG"""
        topology_class_name = None

        #
        # Get config for test from topology
        import sdn_sg_test_topo 
        result = True
        msg = []
        if not topology_class_name:
            topology_class_name = sdn_sg_test_topo.sdn_4vn_xvm_config

        self.logger.info("Scenario for the test used is: %s" %
                         (topology_class_name))
        try:
            # provided by wrapper module if run in parallel test env
            topo = topology_class_name(
                project=self.project.project_name,
                username=self.project.username,
                password=self.project.password, compute_node_list=self.inputs.compute_ips)
        except NameError:
            topo = topology_class_name()

        #
        # Test setup: Configure policy, VN, & VM
        # return {'result':result, 'msg': err_msg, 'data': [self.topo, config_topo]}
        # Returned topo is of following format:
        # config_topo= {'policy': policy_fixt, 'vn': vn_fixture, 'vm': vm_fixture}
        setup_obj = self.useFixture(
            sdnTopoSetupFixture(self.connections, topo))
	out = setup_obj.topo_setup()
        self.logger.info("Setup completed with result %s" % (out['result']))
        self.assertEqual(out['result'], True, out['msg'])
        if out['result']:
            topo_obj, config_topo = out['data']

        self.attach_remove_sg_edit_sg_verify_traffic(topo_obj, config_topo)

        return True
    #end test_SG

#end class SecurityGroupRegressionTests4

class SecurityGroupRegressionTests5(BaseSGTest, VerifySecGroup, ConfigPolicy):

    @classmethod
    def setUpClass(cls):
        super(SecurityGroupRegressionTests5, cls).setUpClass()

    def setUp(self):
        super(SecurityGroupRegressionTests5, self).setUp()
        self.create_sg_test_resources()

    def tearDown(self):
        self.logger.debug("Tearing down SecurityGroupRegressionTests2.")
        super(SecurityGroupRegressionTests5, self).tearDown()

    def runTest(self):
        pass

    @preposttest_wrapper
    def test_sec_group_with_proto_double_rules_sg1(self):
        """Verify security group with allow tcp/udp protocol on all ports and policy with allow all between VN's"""
        self.logger.info("Configure the policy with allow any")
        rules = [
            {
                'direction': '<>',
                'protocol': 'any',
                'source_network': self.vn1_name,
                'src_ports': [0, -1],
                'dest_network': self.vn2_name,
                'dst_ports': [0, -1],
                'simple_action': 'pass',
            },
        ]
        self.config_policy_and_attach_to_vn(rules)
        rule = [{'direction': '<>',
                'protocol': 'tcp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'tcp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 },
		{'direction': '<>',
                'protocol': 'udp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
		{'direction': '<>',
                 'protocol': 'udp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg1_fix.replace_rules(rule)
        rule = [{'direction': '<>',
                'protocol': 'udp',
                 'dst_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'src_addresses': [{'security_group': 'local'}],
                 },
                {'direction': '<>',
                 'protocol': 'udp',
                 'src_addresses': [{'subnet': {'ip_prefix': '10.1.1.0', 'ip_prefix_len': 24}},
                                   {'subnet': {'ip_prefix': '20.1.1.0', 'ip_prefix_len': 24}}],
                 'src_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_ports': [{'start_port': 0, 'end_port': -1}],
                 'dst_addresses': [{'security_group': 'local'}],
                 }]
        self.sg2_fix.replace_rules(rule)

        self.verify_sec_group_port_proto(double_rule=True)
        return True
#end test_sec_group_with_proto_double_rules_sg1

#end class SecurityGroupRegressionTests5

class SecurityGroupRegressionTests6(BaseSGTest, VerifySecGroup, ConfigPolicy):

    @classmethod
    def setUpClass(cls):
        super(SecurityGroupRegressionTests6, cls).setUpClass()

    def runTest(self):
        pass

    @preposttest_wrapper
    def test_sg_stateful(self):
	""" Test if SG is stateful:
	1. test if inbound traffic without allowed ingress rule is allowed
	2. Test if outbound traffic without allowed egress rule is allowed
	3. test traffic betwen SG with only ingress/egress rule"""

        topology_class_name = None

        #
        # Get config for test from topology
        import sdn_sg_test_topo
        result = True
        msg = []
        if not topology_class_name:
            topology_class_name = sdn_sg_test_topo.sdn_topo_config

        self.logger.info("Scenario for the test used is: %s" %
                         (topology_class_name))
	topo = topology_class_name()
        try:
            # provided by wrapper module if run in parallel test env
            topo.build_topo_sg_stateful(
                project=self.project.project_name,
                username=self.project.username,
                password=self.project.password)
        except NameError:
            topo.build_topo_sg_stateful()
        #
        # Test setup: Configure policy, VN, & VM
        # return {'result':result, 'msg': err_msg, 'data': [self.topo, config_topo]}
        # Returned topo is of following format:
        # config_topo= {'policy': policy_fixt, 'vn': vn_fixture, 'vm': vm_fixture}
        setup_obj = self.useFixture(
            sdnTopoSetupFixture(self.connections, topo))
        out = setup_obj.topo_setup()
        self.logger.info("Setup completed with result %s" % (out['result']))
        self.assertEqual(out['result'], True, out['msg'])
        if out['result']:
            topo_obj, config_topo = out['data']

	self.start_traffic_and_verify(topo_obj, config_topo, traffic_reverse=False)
        return True
    #end test_sg_stateful 


#end class SecurityGroupRegressionTests6

