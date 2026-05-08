#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggiorna_dati.py
Script per aggiornare i dati dell'area privata del sito.
Metti questo file nella stessa cartella di dati.json.
Esegui con: python aggiorna_dati.py
"""

import json
import os
from datetime import date

FILE = os.path.join(os.path.dirname(__file__), "dati.json")

def carica():
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def salva(dati):
    dati["aggiornato_il"] = date.today().isoformat()
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
    print("\n✅ dati.json aggiornato con successo.")

def menu_principale(dati):
    while True:
        print("\n" + "="*50)
        print("  GESTIONE AREA PRIVATA — Chiesa Evangelica")
        print("="*50)
        print(f"  Saldo attuale: € {dati['saldo']:.2f}")
        print(f"  Aggiornato il: {dati['aggiornato_il']}")
        print("-"*50)
        print("  1. Aggiorna saldo")
        print("  2. Gestisci spese fisse")
        print("  3. Gestisci riunioni di chiesa")
        print("  4. Gestisci attività")
        print("  5. Gestisci predicazioni")
        print("  6. Salva ed esci")
        print("  0. Esci senza salvare")
        scelta = input("\nScelta: ").strip()

        if scelta == "1":
            aggiorna_saldo(dati)
        elif scelta == "2":
            gestisci_spese(dati)
        elif scelta == "3":
            gestisci_riunioni(dati)
        elif scelta == "4":
            gestisci_attivita(dati)
        elif scelta == "5":
            gestisci_predicazioni(dati)
        elif scelta == "6":
            salva(dati)
            break
        elif scelta == "0":
            print("Uscito senza salvare.")
            break
        else:
            print("Scelta non valida.")

# ── SALDO ────────────────────────────────────────────────────────
def aggiorna_saldo(dati):
    print(f"\nSaldo attuale: € {dati['saldo']:.2f}")
    nuovo = input("Nuovo saldo (€): ").strip().replace(",", ".")
    try:
        dati["saldo"] = round(float(nuovo), 2)
        oggi = date.today()
        # Aggiunge al grafico storico se è il 5 del mese oppure su richiesta
        if "storico_saldo" not in dati:
            dati["storico_saldo"] = []
        aggiungi = False
        if oggi.day == 5:
            aggiungi = True
        else:
            r = input("Vuoi aggiungere questo valore allo storico del grafico? (s/n): ").strip().lower()
            aggiungi = r == "s"
        if aggiungi:
            # evita duplicati sulla stessa data
            dati["storico_saldo"] = [x for x in dati["storico_saldo"] if x["data"] != oggi.isoformat()]
            dati["storico_saldo"].append({"data": oggi.isoformat(), "saldo": dati["saldo"]})
            dati["storico_saldo"].sort(key=lambda x: x["data"])
            print(f"Saldo € {dati['saldo']:.2f} aggiunto allo storico ({oggi.isoformat()}).")
        else:
            print(f"Saldo aggiornato a € {dati['saldo']:.2f} (non aggiunto allo storico).")
    except ValueError:
        print("Valore non valido.")

# ── SPESE FISSE ──────────────────────────────────────────────────
def gestisci_spese(dati):
    while True:
        print("\n--- SPESE FISSE ---")
        for i, s in enumerate(dati["spese_fisse"], 1):
            print(f"  {i}. {s['nome']} — € {s['importo']:.2f} — scadenza: {s['scadenza']}")
        print("\n  A. Aggiungi spesa")
        print("  M. Modifica spesa")
        print("  D. Elimina spesa")
        print("  X. Torna al menu")
        scelta = input("\nScelta: ").strip().upper()

        if scelta == "A":
            aggiungi_spesa(dati)
        elif scelta == "M":
            modifica_spesa(dati)
        elif scelta == "D":
            elimina_spesa(dati)
        elif scelta == "X":
            break

def aggiungi_spesa(dati):
    print("\n-- Nuova spesa fissa --")
    nome     = input("Nome: ").strip()
    importo  = input("Importo (€): ").strip().replace(",", ".")
    scadenza = input("Scadenza (es. 2027-06-01 oppure mensile-15): ").strip()
    note     = input("Note (lascia vuoto se nessuna): ").strip()
    try:
        dati["spese_fisse"].append({
            "nome": nome,
            "importo": round(float(importo), 2),
            "tipo_rinnovo": "automatico",
            "scadenza": scadenza,
            "note": note
        })
        print("Spesa aggiunta.")
    except ValueError:
        print("Importo non valido.")

def modifica_spesa(dati):
    n = input("Numero spesa da modificare: ").strip()
    try:
        idx = int(n) - 1
        s = dati["spese_fisse"][idx]
        print(f"Modifica: {s['nome']}")
        campo = input("Campo da modificare (nome/importo/scadenza/note): ").strip().lower()
        if campo in s:
            nuovo = input(f"Nuovo valore [{s[campo]}]: ").strip()
            if campo == "importo":
                s[campo] = round(float(nuovo.replace(",", ".")), 2)
            else:
                s[campo] = nuovo
            print("Modificato.")
        else:
            print("Campo non valido.")
    except (ValueError, IndexError):
        print("Numero non valido.")

def elimina_spesa(dati):
    n = input("Numero spesa da eliminare: ").strip()
    try:
        idx = int(n) - 1
        rimossa = dati["spese_fisse"].pop(idx)
        print(f"Rimossa: {rimossa['nome']}")
    except (ValueError, IndexError):
        print("Numero non valido.")

# ── RIUNIONI ─────────────────────────────────────────────────────
def gestisci_riunioni(dati):
    while True:
        print("\n--- RIUNIONI DI CHIESA ---")
        for i, r in enumerate(dati["riunioni"], 1):
            stato = "✅" if r["testo"] else "⬜ (vuoto)"
            print(f"  {i}. {r['data']} — {r['titolo']} {stato}")
        print("\n  A. Aggiungi riunione")
        print("  T. Inserisci/modifica testo riunione")
        print("  D. Elimina riunione")
        print("  X. Torna al menu")
        scelta = input("\nScelta: ").strip().upper()

        if scelta == "A":
            aggiungi_riunione(dati)
        elif scelta == "T":
            modifica_testo_riunione(dati)
        elif scelta == "D":
            elimina_riunione(dati)
        elif scelta == "X":
            break

def aggiungi_riunione(dati):
    print("\n-- Nuova riunione --")
    data   = input("Data (AAAA-MM-GG, es. 2026-05-10): ").strip()
    titolo = input("Titolo (es. Riunione di chiesa del 10 maggio 2026): ").strip()
    print("Testo del verbale (premi Invio due volte per finire):")
    righe = []
    while True:
        riga = input()
        if riga == "" and righe and righe[-1] == "":
            break
        righe.append(riga)
    testo = "\n".join(righe).strip()
    dati["riunioni"].insert(0, {"data": data, "titolo": titolo, "testo": testo})
    # ordina per data decrescente
    dati["riunioni"].sort(key=lambda x: x["data"], reverse=True)
    print("Riunione aggiunta.")

def modifica_testo_riunione(dati):
    n = input("Numero riunione: ").strip()
    try:
        idx = int(n) - 1
        r = dati["riunioni"][idx]
        print(f"\nRiunione: {r['titolo']}")
        if r["testo"]:
            print(f"Testo attuale:\n{r['testo']}\n")
        print("Inserisci nuovo testo (premi Invio due volte per finire):")
        righe = []
        while True:
            riga = input()
            if riga == "" and righe and righe[-1] == "":
                break
            righe.append(riga)
        r["testo"] = "\n".join(righe).strip()
        print("Testo aggiornato.")
    except (ValueError, IndexError):
        print("Numero non valido.")

def elimina_riunione(dati):
    n = input("Numero riunione da eliminare: ").strip()
    try:
        idx = int(n) - 1
        rimossa = dati["riunioni"].pop(idx)
        print(f"Rimossa: {rimossa['titolo']}")
    except (ValueError, IndexError):
        print("Numero non valido.")

# ── ATTIVITÀ ─────────────────────────────────────────────────────
def gestisci_attivita(dati):
    if "attivita" not in dati:
        dati["attivita"] = []
    while True:
        print("\n--- ATTIVITÀ PROMOSSE ---")
        for i, a in enumerate(dati["attivita"], 1):
            print(f"  {i}. [{a['stato']}] {a['nome']} — {a['responsabile']}")
        print("\n  A. Aggiungi attività")
        print("  M. Modifica attività")
        print("  D. Elimina attività")
        print("  X. Torna al menu")
        scelta = input("\nScelta: ").strip().upper()

        if scelta == "A":
            aggiungi_attivita(dati)
        elif scelta == "M":
            modifica_attivita(dati)
        elif scelta == "D":
            elimina_attivita(dati)
        elif scelta == "X":
            break

def aggiungi_attivita(dati):
    print("\n-- Nuova attività --")
    nome         = input("Nome attività: ").strip()
    descrizione  = input("Descrizione: ").strip()
    responsabile = input("Responsabile: ").strip()
    print("Stato: 1) In corso  2) In attesa  3) Completata  4) Annullata")
    stati = {"1": "in_corso", "2": "in_attesa", "3": "completata", "4": "annullata"}
    s = input("Scelta [1]: ").strip() or "1"
    stato = stati.get(s, "in_attesa")
    dati["attivita"].append({
        "nome": nome,
        "descrizione": descrizione,
        "responsabile": responsabile,
        "stato": stato
    })
    print("Attività aggiunta.")

def modifica_attivita(dati):
    n = input("Numero attività da modificare: ").strip()
    try:
        idx = int(n) - 1
        a = dati["attivita"][idx]
        print(f"Modifica: {a['nome']}")
        print("Campo: 1) Nome  2) Descrizione  3) Responsabile  4) Stato")
        c = input("Scelta: ").strip()
        if c == "1":
            a["nome"] = input(f"Nome [{a['nome']}]: ").strip() or a["nome"]
        elif c == "2":
            a["descrizione"] = input(f"Descrizione [{a['descrizione']}]: ").strip() or a["descrizione"]
        elif c == "3":
            a["responsabile"] = input(f"Responsabile [{a['responsabile']}]: ").strip() or a["responsabile"]
        elif c == "4":
            print("Stato: 1) In corso  2) In attesa  3) Completata  4) Annullata")
            stati = {"1": "in_corso", "2": "in_attesa", "3": "completata", "4": "annullata"}
            s = input("Scelta: ").strip()
            a["stato"] = stati.get(s, a["stato"])
        print("Modificato.")
    except (ValueError, IndexError):
        print("Numero non valido.")

def elimina_attivita(dati):
    n = input("Numero attività da eliminare: ").strip()
    try:
        idx = int(n) - 1
        rimossa = dati["attivita"].pop(idx)
        print(f"Rimossa: {rimossa['nome']}")
    except (ValueError, IndexError):
        print("Numero non valido.")

# ── PREDICAZIONI ─────────────────────────────────────────────────
def gestisci_predicazioni(dati):
    if "predicazioni" not in dati:
        dati["predicazioni"] = []
    while True:
        print("\n--- PREDICAZIONI ---")
        for i, p in enumerate(dati["predicazioni"], 1):
            stato = "✅" if p.get("predicatore") else "⬜"
            print(f"  {i}. {stato} {p['data']} — {p.get('predicatore','(vuoto)')}")
        print("\n  A. Aggiungi predicazione")
        print("  M. Modifica predicazione")
        print("  D. Elimina predicazione")
        print("  X. Torna al menu")
        scelta = input("\nScelta: ").strip().upper()
        if scelta == "A":
            aggiungi_predicazione(dati)
        elif scelta == "M":
            modifica_predicazione(dati)
        elif scelta == "D":
            elimina_predicazione(dati)
        elif scelta == "X":
            break

def aggiungi_predicazione(dati):
    print("\n-- Nuova predicazione --")
    data        = input("Data (AAAA-MM-GG): ").strip()
    predicatore = input("Predicatore: ").strip()
    riassunto   = input("Riassunto breve: ").strip()
    pdf         = input("Nome file PDF (es. pred_20260419.pdf, lascia vuoto se assente): ").strip()
    dati["predicazioni"].insert(0, {
        "data": data, "predicatore": predicatore,
        "riassunto": riassunto, "pdf": pdf
    })
    dati["predicazioni"].sort(key=lambda x: x["data"], reverse=True)
    print("Predicazione aggiunta.")

def modifica_predicazione(dati):
    n = input("Numero predicazione: ").strip()
    try:
        idx = int(n) - 1
        p = dati["predicazioni"][idx]
        print(f"Modifica: {p['data']} — {p.get('predicatore','')}")
        print("Campo: 1) Data  2) Predicatore  3) Riassunto  4) PDF")
        c = input("Scelta: ").strip()
        if c == "1":
            p["data"] = input(f"Data [{p['data']}]: ").strip() or p["data"]
        elif c == "2":
            p["predicatore"] = input(f"Predicatore [{p.get('predicatore','')}]: ").strip()
        elif c == "3":
            p["riassunto"] = input(f"Riassunto [{p.get('riassunto','')}]: ").strip()
        elif c == "4":
            p["pdf"] = input(f"PDF [{p.get('pdf','')}]: ").strip()
        print("Modificato.")
    except (ValueError, IndexError):
        print("Numero non valido.")

def elimina_predicazione(dati):
    n = input("Numero predicazione da eliminare: ").strip()
    try:
        idx = int(n) - 1
        rimossa = dati["predicazioni"].pop(idx)
        print(f"Rimossa: {rimossa['data']}")
    except (ValueError, IndexError):
        print("Numero non valido.")

# ── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.path.exists(FILE):
        print(f"❌ File non trovato: {FILE}")
        print("Assicurati che aggiorna_dati.py sia nella stessa cartella di dati.json")
    else:
        dati = carica()
        menu_principale(dati)
