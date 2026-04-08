import unittest
from unittest.mock import patch

from cyberdeck import net


class NetBehaviorTests(unittest.TestCase):
    def test_iface_names_with_default_gateway_parses_active_windows_adapter(self):
        sample = """
===========================================================================
IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      192.168.0.1    192.168.0.201     45
          0.0.0.0          0.0.0.0         On-link        172.19.0.1      0
===========================================================================
"""
        with patch("cyberdeck.net.os.name", "nt"), patch(
            "cyberdeck.net.subprocess.check_output",
            return_value=sample,
        ), patch.object(
            net,
            "_iface_name_for_ipv4",
            side_effect=lambda ip: {"192.168.0.201": "Беспроводная сеть", "172.19.0.1": "tun0"}.get(ip, ""),
        ):
            self.assertEqual(net._iface_names_with_default_gateway(), {"Беспроводная сеть"})

    def test_get_local_ip_keeps_route_ip_when_ignore_vpn_is_disabled(self):
        with patch.object(net, "_probe_route_ip", return_value="100.64.1.2"), patch.object(
            net,
            "_iter_non_vpn_ipv4",
            return_value=iter(["192.168.50.10"]),
        ), patch.object(net, "_env_bool", return_value=False), patch.object(
            net,
            "_route_ip_requires_lan_fallback",
            return_value=False,
        ):
            self.assertEqual(net.get_local_ip(), "100.64.1.2")

    def test_get_local_ip_prefers_non_vpn_interface_when_ignore_vpn_is_enabled(self):
        with patch.object(net, "_probe_route_ip", return_value="100.64.1.2"), patch.object(
            net,
            "_iter_non_vpn_ipv4",
            return_value=iter(["192.168.50.10"]),
        ), patch.object(net, "_env_bool", return_value=True), patch.object(
            net,
            "_route_ip_requires_lan_fallback",
            return_value=False,
        ):
            self.assertEqual(net.get_local_ip(), "192.168.50.10")

    def test_get_local_ip_falls_back_to_route_ip_when_ignore_vpn_is_enabled_but_no_lan_found(self):
        with patch.object(net, "_probe_route_ip", return_value="10.8.0.2"), patch.object(
            net,
            "_iter_non_vpn_ipv4",
            return_value=iter([]),
        ), patch.object(net, "_env_bool", return_value=True), patch.object(
            net,
            "_route_ip_requires_lan_fallback",
            return_value=False,
        ):
            self.assertEqual(net.get_local_ip(), "10.8.0.2")

    def test_get_local_ip_falls_back_to_real_lan_when_route_ip_is_virtual_even_without_ignore_vpn(self):
        with patch.object(net, "_probe_route_ip", return_value="172.19.0.1"), patch.object(
            net,
            "_iter_non_vpn_ipv4",
            return_value=iter(["192.168.0.201"]),
        ), patch.object(net, "_env_bool", return_value=False), patch.object(
            net,
            "_route_ip_requires_lan_fallback",
            return_value=True,
        ):
            self.assertEqual(net.get_local_ip(), "192.168.0.201")

    def test_route_ip_requires_lan_fallback_when_interface_has_no_default_gateway(self):
        with patch.object(net, "_iface_name_for_ipv4", return_value="Ethernet 2"), patch.object(
            net,
            "_iface_names_with_default_gateway",
            return_value={"Беспроводная сеть"},
        ):
            self.assertTrue(net._route_ip_requires_lan_fallback("192.168.56.1"))


if __name__ == "__main__":
    unittest.main()
