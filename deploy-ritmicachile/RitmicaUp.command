#!/bin/bash
# 1. Ir a la carpeta
cd /Users/gugasito/Documents/proyectos/git/RitmicaChile/deploy-ritmicachile

# 2. Levantar Docker
docker compose up -d

echo "------------------------------------------"
echo "🚀 RitmicaChile está subiendo..."
echo "⏳ Esperando 5 segundos para abrir la web..."
echo "------------------------------------------"

# 3. Esperar un poco y abrir el navegador
sleep 5
open "http://localhost:4200/"

# 4. Cerrar la terminal automáticamente
exit
EOF
chmod +x ~/Desktop/RitmicaUp.command