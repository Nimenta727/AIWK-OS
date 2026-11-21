---
name: diagnose-network
title: Diagnose why the network does not work
keywords: network, wifi, internet, offline, 网络, 联网, 断网
requires: network.status, system.info
---
1. Read network.status: is there an interface, an address and a default route?
2. If no address: the link is down or Wi-Fi is not connected; point the user to System > Network.
3. If an address but no route: DHCP failed; suggest reconnecting.
4. Do not change settings; report what was found and the single next step.
