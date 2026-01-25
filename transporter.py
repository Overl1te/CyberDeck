import http.server
import socketserver
import sys
import os

# Использование: python transporter.py <путь_к_файлу> <порт>

if __name__ == "__main__":
    try:
        file_path = sys.argv[1]
        port = int(sys.argv[2])
        
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        
        # Переходим в папку с файлом, чтобы раздавать его
        os.chdir(directory)
        
        # Создаем простой обработчик
        Handler = http.server.SimpleHTTPRequestHandler
        
        # Запускаем сервер
        # Он будет работать, пока его не убьет main.py (через terminate)
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
            print(f"Serving {filename} on port {port}")
            httpd.serve_forever()
            
    except Exception as e:
        print(f"Transporter Error: {e}")