from cloudbridge.cloud.interfaces.resources import FloatingIP
from cloudbridge.cloud.interfaces.resources import Network
from cloudbridge.cloud.interfaces.resources import RouterState
from cloudbridge.cloud.interfaces.resources import Subnet

import test.helpers as helpers
from test.helpers import ProviderTestBase
from test.helpers import get_provider_test_data
from test.helpers import standard_interface_tests as sit


class CloudNetworkServiceTestCase(ProviderTestBase):

    _multiprocess_can_split_ = True

    @helpers.skipIfNoService(['networking.networks'])
    def test_crud_network(self):

        def create_net(label):
            return self.provider.networking.networks.create(
                label=label, cidr_block='10.0.0.0/16')

        def cleanup_net(net):
            if net:
                self.provider.networking.networks.delete(network_id=net.id)

        sit.check_crud(self, self.provider.networking.networks, Network,
                       "cb-crudnetwork", create_net, cleanup_net)

    @helpers.skipIfNoService(['networking.networks'])
    def test_network_properties(self):
        label = 'cb-propnetwork-{0}'.format(helpers.get_uuid())
        subnet_label = 'cb-propsubnet-{0}'.format(helpers.get_uuid())
        net = self.provider.networking.networks.create(
            label=label, cidr_block='10.0.0.0/16')
        with helpers.cleanup_action(
            lambda: net.delete()
        ):
            net.wait_till_ready()
            self.assertEqual(
                net.state, 'available',
                "Network in state '%s', yet should be 'available'" % net.state)

            sit.check_repr(self, net)

            self.assertIn(
                net.cidr_block, ['', '10.0.0.0/16'],
                "Network CIDR %s does not contain the expected value."
                % net.cidr_block)

            cidr = '10.0.1.0/24'
            sn = net.create_subnet(
                label=subnet_label, cidr_block=cidr,
                zone=helpers.get_provider_test_data(self.provider,
                                                    'placement'))
            with helpers.cleanup_action(lambda: sn.delete()):
                self.assertTrue(
                    sn in net.subnets,
                    "Subnet ID %s should be listed in network subnets %s."
                    % (sn.id, net.subnets))

                self.assertTrue(
                    sn in self.provider.networking.subnets.list(network=net),
                    "Subnet ID %s should be included in the subnets list %s."
                    % (sn.id, self.provider.networking.subnets.list(net))
                )

                self.assertListEqual(
                    net.subnets, [sn],
                    "Network should have exactly one subnet: %s." % sn.id)

                self.assertIn(
                    net.id, sn.network_id,
                    "Network ID %s should be specified in the subnet's network"
                    " id %s." % (net.id, sn.network_id))

                self.assertEqual(
                    cidr, sn.cidr_block,
                    "Subnet's CIDR %s should match the specified one %s." % (
                        sn.cidr_block, cidr))

    def test_crud_subnet(self):
        # Late binding will make sure that create_subnet gets the
        # correct value
        net = None

        def create_subnet(label):
            return self.provider.networking.subnets.create(
                network=net, cidr_block="10.0.0.0/24", label=label,
                zone=helpers.get_provider_test_data(
                    self.provider, 'placement'))

        def cleanup_subnet(subnet):
            if subnet:
                self.provider.networking.subnets.delete(subnet=subnet)

        net_label = 'cb-crudsubnet-{0}'.format(helpers.get_uuid())
        net = self.provider.networking.networks.create(
            label=net_label, cidr_block='10.0.0.0/16')
        with helpers.cleanup_action(
            lambda:
                self.provider.networking.networks.delete(network_id=net.id)
        ):
            sit.check_crud(self, self.provider.networking.subnets, Subnet,
                           "cb-crudsubnet", create_subnet, cleanup_subnet)

    def test_crud_floating_ip(self):
        net, gw = helpers.get_test_gateway(
            self.provider, 'cb-crudfipgw-{0}'.format(helpers.get_uuid()))

        def create_fip(label):
            fip = gw.floating_ips.create()
            return fip

        def cleanup_fip(fip):
            if fip:
                gw.floating_ips.delete(fip.id)

        with helpers.cleanup_action(
                lambda: helpers.delete_test_gateway(net, gw)):
            sit.check_crud(self, gw.floating_ips, FloatingIP,
                           "cb-crudfip", create_fip, cleanup_fip,
                           skip_name_check=True, supports_labels=False)

    def test_floating_ip_properties(self):
        # Check floating IP address
        net, gw = helpers.get_test_gateway(
            self.provider, 'cb-crudfipgw-{0}'.format(helpers.get_uuid()))
        fip = gw.floating_ips.create()
        with helpers.cleanup_action(
                lambda: helpers.delete_test_gateway(net, gw)):
            with helpers.cleanup_action(lambda: fip.delete()):
                fipl = list(gw.floating_ips)
                self.assertIn(fip, fipl)
                # 2016-08: address filtering not implemented in moto
                # empty_ipl = self.provider.network.floating_ips('dummy-net')
                # self.assertFalse(
                #     empty_ipl,
                #     "Bogus network should not have any floating IPs: {0}"
                #     .format(empty_ipl))
                self.assertFalse(
                    fip.private_ip,
                    "Floating IP should not have a private IP value ({0})."
                    .format(fip.private_ip))
                self.assertFalse(
                    fip.in_use,
                    "Newly created floating IP address should not be in use.")

    @helpers.skipIfNoService(['networking.routers'])
    def test_crud_router(self):

        def _cleanup(net, subnet, router, gateway):
            with helpers.cleanup_action(lambda: net.delete()):
                with helpers.cleanup_action(lambda: subnet.delete()):
                    with helpers.cleanup_action(lambda: gateway.delete()):
                        with helpers.cleanup_action(lambda: router.delete()):
                            router.detach_subnet(subnet)
                            router.detach_gateway(gateway)

        label = 'cb-crudrouter-{0}'.format(helpers.get_uuid())
        # Declare these variables and late binding will allow
        # the cleanup method access to the most current values
        net = None
        sn = None
        router = None
        gteway = None
        with helpers.cleanup_action(lambda: _cleanup(net, sn, router, gteway)):
            net = self.provider.networking.networks.create(
                label=label, cidr_block='10.0.0.0/16')
            router = self.provider.networking.routers.create(network=net,
                                                             label=label)
            cidr = '10.0.1.0/24'
            sn = net.create_subnet(label=label, cidr_block=cidr,
                                   zone=helpers.get_provider_test_data(
                                       self.provider, 'placement'))

            # Check basic router properties
            sit.check_standard_behaviour(
                self, self.provider.networking.routers, router)
            self.assertEqual(
                router.state, RouterState.DETACHED,
                "Router {0} state {1} should be {2}.".format(
                    router.id, router.state, RouterState.DETACHED))

#             self.assertFalse(
#                 router.network_id,
#                 "Router {0} should not be assoc. with a network {1}".format(
#                     router.id, router.network_id))

            router.attach_subnet(sn)
            gteway = net.gateways.get_or_create_inet_gateway(label=label)
            router.attach_gateway(gteway)
            # TODO: add a check for routes after that's been implemented

        sit.check_delete(self, self.provider.networking.routers, router)

    @helpers.skipIfNoService(['networking.networks'])
    def test_default_network(self):
        subnet = self.provider.networking.subnets.get_or_create_default(
            zone=get_provider_test_data(self.provider, 'placement'))
        self.assertIsInstance(subnet, Subnet)
