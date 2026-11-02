# Five-minute pair exercise: ping, then test the application

Pair with a **consenting classmate**, on the teacher-approved classroom network.
Use only your pair's agreed address or the teacher's endpoint. Do not scan nearby
addresses, change managed campus rules, or disable a firewall. If peer access is
blocked, use the supplied class server and compare observations instead.

## 1. Find the relevant LAN IPv4 address (one minute)

Identify the active Wi-Fi/Ethernet interface used for class, not simply the first
private-looking address. Do not give your partner `127.0.0.1` (their own machine),
a Docker/vEthernet bridge, or a VPN interface address. Interface names matter;
campus and container networks can both use private address ranges.

- **Windows:** run `ipconfig`; read the IPv4 address under the active Wi-Fi/Ethernet
  adapter. [Microsoft's ipconfig reference](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ipconfig).
- **Linux:** run `ip -4 address show`; choose the `inet` address on the active LAN
  interface, omitting the `/prefix` suffix. [ip-address manual](https://man7.org/linux/man-pages/man8/ip-address.8.html).
- **macOS:** System Settings → Network → the active Wi-Fi/Ethernet service → Details
  → TCP/IP; read the IPv4 address without changing settings.
  [Apple's TCP/IP settings guide](https://support.apple.com/guide/mac-help/change-tcpip-settings-on-mac-mh14129/mac).

If the interface is unclear, ask the teacher rather than guessing an address.
Exchange addresses privately with your partner; there is no need for a public
list of students' addresses or identities.

## 2. Send four pings (one minute)

Replace `CLASSMATE_IP` with that agreed IPv4 address:

```text
Windows:       ping -n 4 CLASSMATE_IP
Linux/macOS:   ping -c 4 CLASSMATE_IP
```

Replies show ICMP round-trip times, usually in milliseconds. Compare reply count,
loss and variation; four probes are a quick observation, not a capacity test.
Timeouts can mean an unreachable device, a wrong route/interface, or **blocked
ICMP**. They do not establish that HTTP/WebSockets will fail. Sources:
[Windows ping](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/ping),
[Linux iputils ping](https://man7.org/linux/man-pages/man8/ping.8.html),
[Apple's ping manual source](https://github.com/apple-oss-distributions/network_cmds/blob/main/ping.tproj/ping.8).

## 3. Separately check HTTP and the actual port (two minutes)

On the host machine, first open `http://localhost:8000/health`. A running server
returns JSON with `ok: true` and a changing tick. Then, if the teacher permits
peer hosting, bind Python to the approved LAN interface:

```text
python -m multibox.game_server --host YOUR_LAN_IP --port 8000
```

Replace `YOUR_LAN_IP` with the host's approved address. The partner opens
`http://CLASSMATE_IP:8000/health`, then `http://CLASSMATE_IP:8000/` and connects.
For localhost mode on each student's machine, keep the default loopback bind.

**Ping success does not prove TCP port 8000 is open or that Multiboxes is running.**
HTTP success does not by itself prove the WebSocket handshake succeeds. Test the
layers in order, using the exact scheme, address, port and path provided by class.

## 4. Compare one result and use the fallback (one minute)

| Observation | Check next |
| --- | --- |
| Local `/health` fails | Server process, terminal error, install, and the port actually used. Another process may already occupy 8000. |
| Local works, partner fails | Correct LAN interface/address; a server bound only to 127.0.0.1 is local-only. Check the deliberate Docker host-port mapping if using a container. |
| Ping fails but HTTP works | ICMP is probably filtered or handled differently. Continue with the working application; do not disable a firewall to make ping succeed. |
| Ping replies, HTTP fails | TCP port/application can still be closed, bound to the wrong interface, or blocked by a local firewall rule. |
| Both are on Wi-Fi, peer access fails | Campus client isolation/routing may prevent device-to-device traffic. Same SSID does not guarantee peer reachability. Use the teacher's class server. |
| HTTP loads, Connect fails | Full `/ws` URL, matching protocol-v2 client/server, allowed browser origin, and any teacher-managed reverse-proxy WebSocket forwarding. |
| Hosted HTTPS client rejects `ws://` | Use a valid `wss://` certificate/domain endpoint, or open the locally served HTTP client for local WS. Do not ignore certificate or mixed-content checks. |

For a local firewall prompt, follow the teacher's approved process for this app
and selected classroom interface/port. Do not turn off protection globally, add
broad exceptions, or change managed campus rules. Record the symptom for the
teacher/IT and use the class-server fallback. ICMP latency, TCP delivery, server
batching and the client's roughly 100ms interpolation are different components;
none alone measures complete input-to-visible-motion delay.

## Optional: build your own container (10–15 minutes or teacher demo)

Docker is optional for the main practical. Reuse the supplied `Dockerfile`; no
registry publication or campus infrastructure changes are involved.

```sh
docker build -t multiboxes-class .
docker run --rm --name multiboxes-class -p 127.0.0.1:8000:8000 multiboxes-class
```

Open `http://localhost:8000` and reconnect the same browser client. An **image**
is the built filesystem/dependency recipe; a **container** is a running instance.
The Dockerfile installs pinned Python dependencies, copies the client/server,
and starts one authoritative world as a non-root user. Building an image alone
does not start a server. `--rm` removes this container when it exits; the image
remains. Stop this foreground run with Ctrl+C before using port 8000 again.

`HOST_IP:HOST_PORT:CONTAINER_PORT` explains the mapping above. Binding the host
side to **127.0.0.1 intentionally prevents classmates from connecting**. Only for
teacher-approved peer hosting, replace that with the specific approved LAN IP:

```text
docker run --rm --name multiboxes-pair -p YOUR_LAN_IP:8000:8000 multiboxes-class
```

The Python process inside this image already binds `0.0.0.0:8000`; the host-side
mapping is a separate boundary. Do not use a Docker bridge/container address as
the classmate's destination. [Docker's port-publishing explanation](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/)
explains local-only versus selected-interface publishing.

Try one small local rule edit, rebuild the image, stop the old container and run
again. Reconnect and observe the rule change. Old containers/images do not become
new code just because a source file changed. If base-image downloads or Docker
setup consume the session, watch the teacher's demo and complete the Python
starter first. The optional image exercise does not replace campus permission or
TLS preparation in [deployment instructions](deployment.md).
