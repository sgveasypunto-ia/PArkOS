# operacion Specification — HU-F4.1 Vehicle Type Detection

## Purpose

Frontend-side placa validation and vehicle-type detection for the ingreso flow of `web_sucursal`. Establishes the first reusable validation primitive in `src/lib/validation/` and the first generic SWR catalog hook in `src/features/catalogos/hooks/`. Honors A-03 (regex hardcoded, not persisted) and DEC-SUC-22 (no typing tolerance in ingreso).

## Requirements

### Requirement: Placa Normalization Before Regex Match

The system MUST normalize the operator-typed placa before any regex match by applying, in order: `trim()` (start/end whitespace), `toUpperCase()` (case fold), and `replace(/\s+/g, '')` (collapse internal whitespace). The normalized value is the only value passed to the regex test.

#### Scenario: Mixed-case placa normalizes to Auto
- GIVEN the operator typed `"abc123"`
- WHEN `detectarTipoVehiculo("abc123")` is called
- THEN the function returns `'Auto'` (regex matches the uppercased value)

#### Scenario: Leading and trailing whitespace collapses
- GIVEN the operator typed `"  ABC123  "`
- WHEN `detectarTipoVehiculo("  ABC123  ")` is called
- THEN the function returns `'Auto'` (whitespace is trimmed before the regex test)

#### Scenario: Internal whitespace collapses
- GIVEN the operator typed `"AB C123"`
- WHEN `detectarTipoVehiculo("AB C123")` is called
- THEN the function returns `'Auto'` (the internal space is removed before the regex test)

### Requirement: Strict Auto Regex Match

The system MUST match `^[A-Z]{3}[0-9]{3}$` (exported as `REGEX_AUTO`) against the normalized placa. The system MUST NOT apply typing tolerance `O↔0`, `I↔1`, or `B↔8` to the input (DEC-SUC-22).

#### Scenario: Canonical Auto placa matches
- GIVEN the normalized placa is `"ABC123"`
- WHEN the regex test runs
- THEN the function returns `'Auto'`

#### Scenario: Lowercase O inside an Auto candidate does NOT match (no tolerance)
- GIVEN the operator typed `"ABCO23"` (letter O in the digit slot)
- WHEN `detectarTipoVehiculo("ABCO23")` is called
- THEN the function returns `null` (no regex matches; tolerance is forbidden in ingreso per DEC-SUC-22)

### Requirement: Strict Moto Regex Match

The system MUST match `^[A-Z]{3}[0-9]{2}[A-Z]$` (exported as `REGEX_MOTO`) against the normalized placa. The trailing letter MAY be any `[A-Z]` (Colombian motos use mixed formats). Tolerance is forbidden per DEC-SUC-22.

#### Scenario: Canonical Moto placa matches
- GIVEN the normalized placa is `"ABC12D"`
- WHEN the regex test runs
- THEN the function returns `'Moto'`

#### Scenario: Moto variant with non-D trailing letter matches
- GIVEN the normalized placa is `"ABC12E"`
- WHEN `detectarTipoVehiculo("ABC12E")` is called
- THEN the function returns `'Moto'` (the pattern accepts any `[A-Z]` trailing letter)

### Requirement: Invalid Format Returns Null and Surfaces Inline Error

When the normalized value matches neither `REGEX_AUTO` nor `REGEX_MOTO`, the function MUST return `null`. The caller MUST display the inline error message keyed at `operacion.placa_formato_invalido` with literal text `Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)`. The placa field MUST remain open for operator correction.

#### Scenario: 4 letters + 2 digits returns null
- GIVEN the operator typed `"ABCD12"`
- WHEN `detectarTipoVehiculo("ABCD12")` is called
- THEN the function returns `null` and the UI shows the inline error message

#### Scenario: Empty placa returns null
- GIVEN the operator typed `""`
- WHEN `detectarTipoVehiculo("")` is called
- THEN the function returns `null` (no regex matches an empty string)

#### Scenario: Operator may correct after invalid format
- GIVEN the UI displayed the inline error for an invalid format
- WHEN the operator edits the placa field
- THEN the error MUST clear as soon as the new normalized value matches one of the two regexes, without page reload

### Requirement: Catalog Hook Reads From Backend With Hardcoded Fallback

The system MUST expose a SWR hook `useTiposVehiculo()` that reads `GET /api/v1/catalogos/tipos-vehiculo` via `parkosFetch`, dedupes for 5 minutes (`dedupingInterval: 5*60*1000`), and MUST fall back to a hardcoded `{auto, moto}` array when the API is unreachable (5xx, network, or 401 unauthenticated). The hook MUST expose `isFromFallback: boolean` so downstream consumers (F4.3, F6.x) can show a "usando datos locales" tooltip.

#### Scenario: API responds 200 with both tipos vigentes
- GIVEN the operator is authenticated and the API returns `[{tipo: "Auto"}, {tipo: "Moto"}]`
- WHEN the hook renders
- THEN `tipos` contains the API payload and `isFromFallback` is `false`

#### Scenario: API responds 404 (empty catalog at new branch)
- GIVEN the API returns 404 (valid empty-catalog state, not an error)
- WHEN the hook renders
- THEN `tipos` falls back to the hardcoded catalog and `shouldRetryOnError` skips retries

#### Scenario: API unreachable (network error or 5xx)
- GIVEN the local `api-sucursal` is down
- WHEN the hook renders
- THEN `tipos` falls back to the hardcoded catalog and `isFromFallback` is `true` (downstream may show tooltip)

#### Scenario: Operator not authenticated (cold boot)
- GIVEN `useAuthStore.accessToken` is null
- WHEN the hook initializes
- THEN the SWR key is `null` and the hook exposes the hardcoded catalog immediately

### Requirement: Type Tolerance Lives in a Separate Function (DEC-SUC-22)

The system MUST NOT reuse the type-tolerant search `buscarIngresoTolerante()` for vehicle-type detection in the ingreso flow. The two functions MUST live in separate files. Tolerance `O↔0`, `I↔1`, `B↔8` is allowed ONLY in the salida-side search (Fase 7, CU-02/03).

#### Scenario: Tolerance function does not exist in placa.ts
- GIVEN `apps/electron-sucursal/src/lib/validation/placa.ts` is read
- WHEN the file is searched for tolerance patterns (`O↔0`, `I↔1`, `B↔8`, lookup tables, fuzzy match)
- THEN none are present in `placa.ts`

### Requirement: Regex Constants Are Reusable Exports

The system MUST export `REGEX_AUTO` and `REGEX_MOTO` as module-level constants from `placa.ts` so forward consumers (F6.1 `<PlacaInput>` Zod schema) can reuse them without redefining the pattern.

#### Scenario: F6.1 imports REGEX_AUTO for Zod
- GIVEN a future F6.1 file imports `REGEX_AUTO` from `@/lib/validation/placa`
- WHEN the import resolves
- THEN the regex value is identical to the one used by `detectarTipoVehiculo` (single source of truth)