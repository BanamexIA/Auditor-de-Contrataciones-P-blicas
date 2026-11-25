# Cálculo INDEPENDIENTE (no importa agente_deteccion). Fórmulas del plan/diseño:
# mediana y MAD sobre ln(monto); escala = MAD/0.6745; umbral = mediana ± 3.5*escala; se reporta en pesos con exp().
import math
def mediana(xs):
    xs = sorted(xs); n = len(xs); m = n // 2
    return xs[m] if n % 2 else (xs[m-1] + xs[m]) / 2
def analizar(nombre, montos, z=3.5):
    logs = [math.log(m) for m in montos]
    med = mediana(logs); mad = mediana([abs(v - med) for v in logs]); esc = mad / 0.6745
    inf, sup = med - z*esc, med + z*esc
    print(f"\n{nombre}: n={len(montos)} mediana_pesos={mediana(montos):,.2f} mad={mad:.4f}")
    print(f"  umbral_inferior={math.exp(inf):,.2f} umbral_superior={math.exp(sup):,.2f}")
    for m in montos:
        zz = (math.log(m) - med) / esc
        if not (inf <= math.log(m) <= sup):
            print(f"  ATÍPICO {m:>14,.0f}  z={zz:8.2f}  {'alto' if math.log(m)>sup else 'bajo'}  nivel={'alto' if abs(zz)>=2*z else 'medio'}")
analizar("e4_01", [2000,900000,950000,1000000,1000000,1050000,1100000,1150000,1200000,45000000])
analizar("e4_02 (sin atípicos)", [950000,980000,1000000,1000000,1020000,1050000,1070000,1100000,1120000,1150000])
analizar("e4_06 ficha (grupo con empresa y otros)", [1000000,1100000,900000,1050000,950000,1200000,1000000,90000000,500000000])
