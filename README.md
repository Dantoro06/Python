<img width="988" height="430" alt="imagen" src="https://github.com/user-attachments/assets/92ee7c01-102c-47b5-a576-7659a19077b7" /># 🧠 Motor de Riesgo – Hidding Bonus / Self-Hedging / Abuso de Bonos  
### Proyecto Nueve11 – Herramienta de análisis masivo de apuestas deportivas

---

## 🏆 Descripción general

Este proyecto implementa un **motor avanzado de análisis de riesgo** para casas de apuestas online, con capacidades profesionales para detectar:

- **Hidding Bonus / Multiusuario (coberturas 1–X–2)**
- **Self-Hedging (misma cuenta cubriendo múltiples selecciones)**
- **Abuso de bonos (bono de registro, freebets, rollover, etc.)**
- **Cruce con bases externas (KYC, fraude, listas negras)**
- **Análisis masivo de datasets** desde 50K hasta 5M+ de apuestas

El sistema está compuesto por **tres módulos principales**:

1. 🔧 **Motor de Riesgo (motor_hidding_bonus.py)**  
   Lógica completa del análisis, normalización, detección, cálculo y reportes.

2. 🖥 **Aplicación de Escritorio Tkinter (app_hidding_bonus_tk.py)**  
   Interfaz operativa para que analistas carguen archivos y ejecuten reportes.

3. 📊 **Dashboard Streamlit multipage (dashboard_pro/)**  
   Visualización histórica, indicadores y exploración dinámica de resultados.

Este repositorio incluye **solo código**.  
Los datasets grandes se mantienen **locales** y **no se suben** a GitHub por buenas prácticas.

---

## 🚀 Funcionalidades principales

### ✔ Normalización automática de columnas
Acepta variantes como:

- `user_id`, `userid`, `Player Id`, `player_id`
- `bet_type`, `BetType`, `bettype`
- `sport`, `deporte`
- `event_name`, `Partido`, `Match`
- `stake`, `bet_amount`, `bonus_stake`, `freebet_amount`, etc.

### ✔ Filtros y preparación de tabla base

- Solo apuestas simples (single bets)
- Mercados equivalentes a **1X2**
- Extracción de equipos desde nombres de evento
- Cálculo de `total_stake` y `possible_win`
- Limpieza de estado: ganado, perdido, cancelado, pendiente

### ✔ Detección de Multiusuario (Hidding Bonus)

- Agrupación por evento
- Inferencia de selección válida
- Identificación de coberturas 1–X–2 entre múltiples usuarios
- Cálculo de ratios de cobertura
- Identificación de tríos sospechosos

### ✔ Detección de Self-Hedging

- Análisis usuario+evento
- Identifica cuando un mismo usuario cubre varias selecciones
- Calcula exposición, riesgo y posible ganancia

### ✔ Cruce con base de bonos y bases externas

- Detección de abuso de promociones
- Identificación de usuarios con freebets, rollover alto, etc.
- Alias automáticos en columnas (`user_id`, `userid`, `Player Id`, etc.)

### ✔ Reportes automáticos

El motor genera:

- `hidding_bonus_base.xlsx`
- `hidding_bonus_multiusuario.xlsx`
- `hidding_bonus_multiusuario_trios.xlsx`
- `hidding_bonus_selfhedging.xlsx`
- `hidding_bonus_selfhedging_detalle.xlsx`
- Archivos JSON para dashboard histórico

---

## 🏗 Arquitectura del Proyecto
