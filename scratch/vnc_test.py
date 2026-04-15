import socket
import sys

def test_port(host, port, timeout=5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            print(f"Port {port}: OPEN")
            return True
    except socket.timeout:
        print(f"Port {port}: TIMEOUT")
    except ConnectionRefusedError:
        print(f"Port {port}: REFUSED")
    except Exception as e:
        print(f"Port {port}: ERROR ({e})")
    return False

host = "10.102.6.11"
print(f"Testing connectivity to {host}...")
test_port(host, 3306)  # SQL
test_port(host, 5900)  # VNC 0
test_port(host, 5901)  # VNC 1
test_port(host, 5902)  # VNC 2
