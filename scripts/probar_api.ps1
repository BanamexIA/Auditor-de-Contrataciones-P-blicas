# Prueba de punta a punta de la API contra el backend y Postgres reales.
# Uso:  .\scripts\probar_api.ps1                 (local, http://localhost:5000)
#       .\scripts\probar_api.ps1 -Api http://localhost:15000   (EC2 por túnel; -SinDocker)
# Requiere las migraciones 10 a 13 aplicadas. Crea un caso de prueba nuevo en cada corrida.
param(
    [string]$Api = "http://localhost:5000",
    [switch]$SinDocker   # no inserta señal ni reporte (necesitan docker compose exec)
)

$ErrorActionPreference = "Stop"
$script:fallas = 0
$json = "application/json; charset=utf-8"

function Ok($texto)    { Write-Host "  OK    $texto" -ForegroundColor Green }
function Falla($texto) { Write-Host "  FALLA $texto" -ForegroundColor Red; $script:fallas++ }

function Llamar($metodo, $ruta, $cuerpo = $null) {
    $params = @{ Method = $metodo; Uri = "$Api$ruta"; UseBasicParsing = $true }
    if ($null -ne $cuerpo) {
        $params.ContentType = $json
        $params.Body = [Text.Encoding]::UTF8.GetBytes(($cuerpo | ConvertTo-Json -Compress))
    }
    try {
        $r = Invoke-WebRequest @params
        $codigo = [int]$r.StatusCode; $texto = $r.Content
    } catch {
        if (-not $_.Exception.Response) { throw }
        $codigo = [int]$_.Exception.Response.StatusCode
        $texto = $_.ErrorDetails.Message
    }
    $datos = $null
    if ($texto) { try { $datos = $texto | ConvertFrom-Json } catch {} }
    return [pscustomobject]@{ Codigo = $codigo; Datos = $datos }
}

function Esperar($nombre, $r, $codigo, [scriptblock]$condicion = { $true }) {
    if ($r.Codigo -eq $codigo -and (& $condicion $r.Datos)) { Ok "$nombre ($codigo)" }
    else { Falla "${nombre}: se esperaba $codigo y llegó $($r.Codigo) $($r.Datos | ConvertTo-Json -Compress -Depth 5)" }
}

Write-Host "`nSalud" -ForegroundColor Cyan
Esperar "GET /health" (Llamar GET "/health") 200
Esperar "GET /health/db" (Llamar GET "/health/db") 200 { param($d) $d.database -eq "connected" }
if ($script:fallas) { Write-Host "`nEl backend no llega a la base; revisa 'docker compose logs backend'." -ForegroundColor Red; exit 1 }

Write-Host "`nCasos (B2)" -ForegroundColor Cyan
$r = Llamar POST "/casos" @{ solicitud = "Prueba de punta a punta: contratos de la empresa X en 2026" }
Esperar "Crear caso" $r 201 { param($d) $d.estado -eq "recibido" }
$id = $r.Datos.id
Esperar "Ver caso" (Llamar GET "/casos/$id") 200 { param($d) $d.id -eq $id }
Esperar "Listar con filtro" (Llamar GET "/casos?estado=recibido&limite=5") 200 { param($d) $d.casos.Count -ge 1 }
Esperar "Saltar estado" (Llamar POST "/casos/$id/transiciones" @{ estado = "normado" }) 409
Esperar "Bloquear sin motivo" (Llamar POST "/casos/$id/transiciones" @{ estado = "bloqueado" }) 409
Esperar "Avanzar a consultado" (Llamar POST "/casos/$id/transiciones" @{ estado = "consultado" }) 200
Esperar "Bloquear con motivo" (Llamar POST "/casos/$id/transiciones" @{ estado = "bloqueado"; motivo = "Prueba: agente apagado" }) 200 `
    { param($d) $d.estado_previo -eq "consultado" -and $d.motivo_bloqueo }
Esperar "Cerrar bloqueado" (Llamar POST "/casos/$id/transiciones" @{ estado = "cerrado" }) 409
Esperar "Desbloquear" (Llamar POST "/casos/$id/transiciones" @{ estado = "consultado" }) 200 { param($d) -not $d.motivo_bloqueo }
Esperar "Caso inexistente" (Llamar GET "/casos/no-existe") 404 { param($d) $d.error.codigo -eq "caso_no_encontrado" }

$senal = $null
if (-not $SinDocker) {
    Write-Host "`nSeñales y decisiones (B4)" -ForegroundColor Cyan
    $senal = "prueba-$([guid]::NewGuid())"
    # Por stdin: PowerShell 5.1 quita las comillas dobles de los argumentos de programas externos.
    "INSERT INTO audit.senales (id, caso_id, tipo, datos) VALUES ('$senal', '$id', 'adjudicacion_directa_recurrente', '{`"valor`": 0.64, `"umbral`": 0.3}');" |
        docker compose exec -T db psql -q -v ON_ERROR_STOP=1 -U postgres -d auditor_contrataciones | Out-Null
    if ($LASTEXITCODE) { Falla "Insertar señal de prueba (¿aplicaste 12_audit_senales.sql?)"; $senal = $null }
}
if ($senal) {
    $ruta = "/casos/$id/senales/$senal/decision"
    Esperar "Descartar sin comentario" (Llamar POST $ruta @{ decision = "descartada" }) 400
    Esperar "Decidir pendiente" (Llamar POST $ruta @{ decision = "pendiente" }) 201
    Esperar "Cambiar a descartada" (Llamar POST $ruta @{ decision = "descartada"; comentario = "Prueba: proveedor único" }) 201
    Esperar "Ver decisión vigente" (Llamar GET "/casos/$id/senales") 200 `
        { param($d) $d.senales[0].decision.decision -eq "descartada" }
}

if (-not $SinDocker) {
    Write-Host "`nReportes (B5)" -ForegroundColor Cyan
    $py = "from backend.app import engine_desde_entorno; from backend.casos.repositorio import RepositorioCasosSQL; " +
          "from backend.reportes.almacen import almacen_desde_entorno; from backend.reportes.servicio import guardar_reporte; " +
          "guardar_reporte(RepositorioCasosSQL(engine_desde_entorno()), almacen_desde_entorno(), '$id', b'# Reporte de prueba', 'md', modelo='prueba')"
    docker compose exec -T backend python -c $py
    if ($LASTEXITCODE) { Falla "Guardar reporte (¿aplicaste 13_audit_reportes.sql?)" }
    else {
        Esperar "Listar reportes" (Llamar GET "/casos/$id/reportes") 200 { param($d) $d.reportes[0].version -eq 1 }
        $archivo = Invoke-WebRequest "$Api/casos/$id/reportes/1/archivo" -UseBasicParsing
        $contenido = $archivo.Content
        if ($contenido -is [byte[]]) { $contenido = [Text.Encoding]::UTF8.GetString($contenido) }
        if ($contenido -eq "# Reporte de prueba") { Ok "Descargar reporte (200)" }
        else { Falla "Descargar reporte: el contenido no coincide" }
    }
}

Write-Host "`nCierre y bitácora (B2, B3)" -ForegroundColor Cyan
foreach ($estado in "detectado", "normado", "reportado", "en_revision") {
    Esperar "Avanzar a $estado" (Llamar POST "/casos/$id/transiciones" @{ estado = $estado }) 200
}
Esperar "Cerrar" (Llamar POST "/casos/$id/transiciones" @{ estado = "cerrado" }) 200
if ($senal) {
    Esperar "Decidir en caso cerrado" (Llamar POST "/casos/$id/senales/$senal/decision" @{ decision = "relevante" }) 409
}
$r = Llamar GET "/casos/$id/bitacora"
Esperar "Rastro del caso" $r 200 { param($d) $d.eventos[0].evento -eq "solicitud" }
Write-Host ""
$r.Datos.eventos | Format-Table id, etapa, evento, @{ n = "detalle"; e = { $_.detalle | ConvertTo-Json -Compress } } -AutoSize -Wrap

Write-Host "`nErrores (B6)" -ForegroundColor Cyan
Esperar "Ruta inexistente" (Llamar GET "/no-existe") 404 { param($d) $d.error.codigo -eq "ruta_no_encontrada" }
Esperar "Método equivocado" (Llamar DELETE "/casos") 405 { param($d) $d.error.codigo -eq "metodo_no_permitido" }

Write-Host "`nCaso de prueba: $id"
if ($script:fallas) { Write-Host "$($script:fallas) prueba(s) fallaron." -ForegroundColor Red; exit 1 }
Write-Host "Todas las pruebas pasaron." -ForegroundColor Green
