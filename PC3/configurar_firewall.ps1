# Script para configurar el firewall de Windows para el servidor de chat
# Ejecutar como Administrador: PowerShell -ExecutionPolicy Bypass -File configurar_firewall.ps1

Write-Host "Configurando firewall de Windows para el servidor de chat..." -ForegroundColor Green

# Puertos a permitir
$ports = @(
    @{Port=9009; Protocol="TCP"; Name="Chat"},
    @{Port=9010; Protocol="TCP"; Name="Archivos"},
    @{Port=9020; Protocol="UDP"; Name="Video"}
)

foreach ($portConfig in $ports) {
    $port = $portConfig.Port
    $protocol = $portConfig.Protocol
    $name = $portConfig.Name
    
    Write-Host "Configurando puerto $port ($protocol) para $name..." -ForegroundColor Yellow
    
    # Verificar si la regla ya existe
    $existingRule = Get-NetFirewallRule -DisplayName "PC3 Chat Server - $name" -ErrorAction SilentlyContinue
    
    if ($existingRule) {
        Write-Host "  La regla ya existe, eliminando..." -ForegroundColor Gray
        Remove-NetFirewallRule -DisplayName "PC3 Chat Server - $name" -ErrorAction SilentlyContinue
    }
    
    # Crear nueva regla
    New-NetFirewallRule -DisplayName "PC3 Chat Server - $name" `
                        -Direction Inbound `
                        -Protocol $protocol `
                        -LocalPort $port `
                        -Action Allow `
                        -Description "Permite conexiones para el servidor de chat PC3 - $name" | Out-Null
    
    Write-Host "  ✓ Regla creada para puerto $port ($protocol)" -ForegroundColor Green
}

Write-Host "`n¡Configuración completada!" -ForegroundColor Green
Write-Host "Los puertos 9009 (TCP), 9010 (TCP) y 9020 (UDP) están ahora permitidos en el firewall." -ForegroundColor Cyan

