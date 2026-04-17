import os
import socket
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cyberdeck import net


class NetBehaviorTests(unittest.TestCase):
    def test_env_bool_parses_common_values_and_falls_back_for_unknown(self):
        with patch.dict(os.environ, {"CD_TRUE": "yes", "CD_FALSE": "off", "CD_UNKNOWN": "maybe"}, clear=False):
            self.assertTrue(net._env_bool("CD_TRUE", False))
            self.assertFalse(net._env_bool("CD_FALSE", True))
            self.assertTrue(net._env_bool("CD_UNKNOWN", True))
            self.assertFalse(net._env_bool("CD_MISSING", False))

    def test_score_ipv4_candidate_filters_unusable_adapters_and_scores_lan(self):
        self.assertLess(net._score_ipv4_candidate("not-an-ip", "Ethernet"), 0)
        self.assertLess(net._score_ipv4_candidate("127.0.0.1", "Ethernet"), 0)
        self.assertLess(net._score_ipv4_candidate("192.168.0.10", "WireGuard"), 0)
        self.assertLess(net._score_ipv4_candidate("192.168.0.10", "vEthernet Default Switch"), 0)
        self.assertGreater(net._score_ipv4_candidate("192.168.0.10", "Wi-Fi"), 100)

    def test_iter_non_vpn_ipv4_ranks_gateway_and_filters_virtual_interfaces(self):
        wifi = SimpleNamespace(family=socket.AF_INET, address="192.168.0.201")
        ethernet = SimpleNamespace(family=socket.AF_INET, address="10.0.0.20")
        virtual = SimpleNamespace(family=socket.AF_INET, address="172.19.0.1")
        ipv6 = SimpleNamespace(family=socket.AF_INET6, address="fe80::1")
        stats = {
            "Wi-Fi": SimpleNamespace(isup=True, speed=866),
            "Ethernet": SimpleNamespace(isup=True, speed=1000),
            "vEthernet Default Switch": SimpleNamespace(isup=True, speed=10000),
            "Downlink": SimpleNamespace(isup=False, speed=1000),
        }
        addrs = {
            "Wi-Fi": [wifi, ipv6],
            "Ethernet": [ethernet],
            "vEthernet Default Switch": [virtual],
            "Downlink": [SimpleNamespace(family=socket.AF_INET, address="192.168.50.3")],
        }
        with patch("cyberdeck.net.psutil.net_if_addrs", return_value=addrs), patch(
            "cyberdeck.net.psutil.net_if_stats",
            return_value=stats,
        ), patch.object(net, "_default_gateway_route_ips", return_value={"10.0.0.20"}):
            self.assertEqual(list(net._iter_non_vpn_ipv4(preferred_ip="192.168.0.201")), ["10.0.0.20", "192.168.0.201"])

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
