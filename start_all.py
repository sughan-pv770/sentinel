import subprocess
import os
import sys

def main():
    print("Starting SentinelX servers...")
    root = os.path.dirname(os.path.abspath(__file__))
    
    print("Installing demo-service dependencies...")
    demo_cwd = os.path.join(root, 'demo-service')
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=demo_cwd)
    
    print("Starting demo-service on port 9000...")
    demo_env = os.environ.copy()
    demo_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"], 
        cwd=demo_cwd, 
        env=demo_env
    )
    
    print("Installing gateway dependencies...")
    gate_cwd = os.path.join(root, 'gateway')
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=gate_cwd)
    
    print("Installing orbit dependencies...")
    orbit_cwd = os.path.join(root, 'orbit')
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=orbit_cwd)

    print("Installing stub-service dependencies...")
    stub_cwd = os.path.join(root, 'stub-service')
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=stub_cwd)
    
    print("Starting gateway on port 8080...")
    gate_env = os.environ.copy()
    gate_env["SENTINELX_ORIGIN_BASE_URL"] = "http://localhost:9000"
    gate_env["SENTINELX_ORBIT_BASE_URL"] = "http://localhost:9001"
    gate_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"], 
        cwd=gate_cwd, 
        env=gate_env
    )
    
    print("Starting orbit on port 9001...")
    orbit_env = os.environ.copy()
    orbit_env["GATEWAY_URL"] = "http://localhost:8080"
    orbit_env["ORBIT_ENV"] = "demo"
    orbit_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001", "--reload"], 
        cwd=orbit_cwd, 
        env=orbit_env
    )

    print("Starting stub-service on port 9002...")
    stub_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9002", "--reload"], 
        cwd=stub_cwd,
        env=os.environ.copy()
    )
    
    print("\n[OK] All servers started!")
    print("  Gateway:       http://localhost:8080")
    print("  Demo Service:  http://localhost:9000")
    print("  Orbit SaaS:    http://localhost:9001")
    print("  Stub Service:  http://localhost:9002")
    print("\nPress Ctrl+C to stop all servers.\n")
    try:
        demo_process.wait()
        gate_process.wait()
        orbit_process.wait()
        stub_process.wait()
    except KeyboardInterrupt:
        print("\nStopping all servers...")
        demo_process.terminate()
        gate_process.terminate()
        orbit_process.terminate()
        stub_process.terminate()

if __name__ == "__main__":
    main()
