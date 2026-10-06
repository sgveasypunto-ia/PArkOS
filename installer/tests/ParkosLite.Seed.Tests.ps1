# Tests estaticos de installer/lite/seed_demo.sql: el seed debe ser re-ejecutable
# y respetar el modelo bi-temporal (AGENTS.md): nunca borra, nunca hace
# ON CONFLICT sobre vigente_desde y cada tabla [V] se inserta con NOT EXISTS
# sobre la version vigente. No necesita Postgres.

$script:sql = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '..\lite\seed_demo.sql')
# Sin comentarios `-- ...` para no confundir prosa con sentencias.
$script:code = ($script:sql -split "`r?`n" | Where-Object { $_ -notmatch '^\s*--' }) -join "`n"

Describe 'seed_demo.sql' {
    It 'no contiene DELETE ni TRUNCATE' {
        $script:code | Should Not Match '(?i)\bDELETE\b'
        $script:code | Should Not Match '(?i)\bTRUNCATE\b'
    }
    It 'nunca usa ON CONFLICT (vigente_desde cambia en cada corrida)' {
        $script:code | Should Not Match '(?i)ON\s+CONFLICT'
    }
    It 'cada INSERT sobre tablas [V] esta protegido con NOT EXISTS' {
        $inserts = [regex]::Matches($script:code, '(?is)INSERT\s+INTO\s+prod\.(\w+).*?;')
        $inserts.Count | Should BeGreaterThan 5
        foreach ($m in $inserts) {
            $m.Value | Should Match '(?i)NOT\s+EXISTS'
        }
    }
    It 'las UPDATE solo cierran versiones (vigente_hasta + estado inactivo)' {
        foreach ($m in [regex]::Matches($script:code, '(?is)UPDATE\s+prod\.\w+.*?;')) {
            $m.Value | Should Match '(?i)SET\s+vigente_hasta\s*=\s*NOW\(\),\s*estado\s*=\s*''inactivo'''
            $m.Value | Should Match '(?i)vigente_hasta\s+IS\s+NULL'
        }
    }
    It 'siembra UNA tarifa por tipo de vehiculo, por minuto y con tope valor_plena' {
        # calcular_cotizacion toma una sola tarifa y cobra valor * CEIL(minutos).
        $block = [regex]::Match($script:code, '(?is)CREATE TEMP TABLE _demo_tarifas \(.*?;\s*INSERT INTO _demo_tarifas VALUES(.*?);').Groups[1].Value
        $block | Should Not BeNullOrEmpty
        foreach ($v in 'carro', 'moto') {
            $block | Should Match "'$v',\s*\d+,\s*\d+"
        }
        $script:code | Should Match "tt\.tipo = 'hora'"
    }
}
