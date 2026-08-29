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
    
    print("Starting gateway on port 8080...")
    gate_env = os.environ.copy()
    gate_env["SENTINELX_ORIGIN_BASE_URL"] = "http://localhost:9000"
    gate_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"], 
        cwd=gate_cwd, 
        env=gate_env
    )
    
    print("Both servers started! Press Ctrl+C to stop.")
    try:
        demo_process.wait()
        gate_process.wait()
    except KeyboardInterrupt:
        print("Stopping servers...")
        demo_process.terminate()
        gate_process.terminate()

if __name__ == "__main__":
    main()
