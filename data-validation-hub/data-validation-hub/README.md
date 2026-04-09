# Data Validation Hub — POC Retail

## Setup rapido

### Prerequisiti
- **Node.js** ≥ 18 (scarica da https://nodejs.org)
- **VS Code**

### Installazione

1. Apri la cartella `data-validation-hub` in VS Code

2. Apri il terminale integrato (`Ctrl+ò` oppure `Terminal → New Terminal`)

3. Installa le dipendenze:
```bash
npm install
```

4. Avvia il dev server:
```bash
npm run dev
```

5. Si apre automaticamente il browser su `http://localhost:3000`

### Supabase

Prima di usare l'app, assicurati di aver eseguito nel SQL Editor di Supabase:

1. La **DDL** (`supabase_target_schema.sql`) per creare le tabelle
2. Il **disable RLS** (`supabase_disable_rls.sql`) per permettere gli insert

Le credenziali Supabase sono già configurate nel codice.

### Struttura

```
data-validation-hub/
├── index.html                    # Entry point HTML
├── package.json                  # Dipendenze (React + Vite)
├── vite.config.js                # Config Vite
├── src/
│   ├── main.jsx                  # Bootstrap React
│   └── DataValidationHub.jsx     # Componente principale
└── sample_datasets/              # Dataset di esempio (copiati a parte)
```

### Uso

1. Vai su **Upload** → trascina un file (CSV, JSON, JSONL, XML, XLSX)
2. Il sistema rileva automaticamente la tabella target
3. Clicca **Avvia Validazione** → la pipeline esegue:
   - Ingestion + mapping colonne → schema DDL
   - Type casting e validazione constraint
   - Auto-fix issue non critiche
   - Alert per issue critiche
4. Nei **Risultati** puoi:
   - Scaricare il JSONL validato
   - Caricare direttamente su Supabase
   - Verificare il mapping e le issue
