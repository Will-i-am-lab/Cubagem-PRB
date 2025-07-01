from flask import Flask, render_template, request, send_file
import pandas as pd
import os
 
app = Flask(__name__)
 
@app.route('/')
def index():
    return render_template('index.html')
 
@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if file.filename.endswith('.xlsx'):
        df = pd.read_excel(file)
        df.to_pickle('temp_df.pkl')
        bcs = df['BC'].unique().tolist()
 
        capacidad_default = {
            'MST': [11],
            'TAC': [21],
            'HCI': [22, 11],
            'PRM': [20],
            'IDL': [22, 10],
            'WYB': [21, 10],
        }
 
        return render_template('select_capacities.html',
                               bcs=bcs,
                               capacidad_default=capacidad_default)
    return 'Por favor sube un archivo .xlsx válido ❌'
 
@app.route('/optimize', methods=['POST'])
def optimize():
    df = pd.read_pickle('temp_df.pkl')
    df['Pallets restantes'] = df['Pallets']
 
    # Leemos capacidades elegidas por BC
    capacidad_por_bc = {}
    for bc in df['BC'].unique():
        cantidades = request.form.get(bc).split(',')
        capacidad_por_bc[bc] = [int(x) for x in cantidades if x.strip()]
 
    contenedores = []
    cont_num = 1
 
    # Por cada BC
    for bc in df['BC'].unique():
        grupo = df[df['BC'] == bc].copy()
 
        # Mientras queden pallets
        while grupo['Pallets restantes'].sum() > 0:
            sum_rem = grupo['Pallets restantes'].sum()
            caps = capacidad_por_bc[bc]
 
            # Selección de capacidad: maximizar llenado
            if sum_rem >= max(caps):
                cap_sel = max(caps)
            else:
                cap_sel = min(caps, key=lambda c: abs(c - sum_rem))
 
            pallets_actuales = 0
            seleccion = []
            skus = set()
 
            # Orden por Lead time + pallets restantes
            grupo = grupo.sort_values(['Lead time','Pallets restantes'],
                                      ascending=[True, False])
 
            # Asignación de pallets al contenedor
            for idx, row in grupo.iterrows():
                if row['Pallets restantes'] <= 0:
                    continue
 
                sku = row['SKU']
                nombre = row['Nombre SKU']
 
                # ⛔ Límite de 5 SKUs (solo si ya llenamos casi al 100%)
                if len(skus) >= 5 and pallets_actuales < cap_sel * 0.9:
                    # si no hemos llenado por lo menos el 90%, ignoramos el tope
                    pass
                elif len(skus) >= 5 and sku not in skus:
                    continue
 
                espacio = cap_sel - pallets_actuales
                if espacio <= 0:
                    break
 
                take = min(row['Pallets restantes'], espacio)
                cajas = take * row['Cajas por Pallet']
 
                seleccion.append({
                    'SKU': sku,
                    'Nombre SKU': nombre,
                    'BC': bc,
                    'Pallets asignados': take,
                    'Cajas asignadas': cajas,
                    'Lead time': row['Lead time'],
                    'Contenedor': cont_num
                })
                pallets_actuales += take
                skus.add(sku)
 
                # Actualizamos en dataframes
                grupo.at[idx,'Pallets restantes'] -= take
                df.at[idx,'Pallets restantes']   -= take
 
                if pallets_actuales >= cap_sel:
                    break
 
            # Guardamos si hubo asignaciones
            if seleccion:
                contenedores.append(pd.DataFrame(seleccion))
                cont_num += 1
            else:
                break
 
    # Exportar Excel
    resultado = pd.concat(contenedores, ignore_index=True)
    resultado.to_excel('resultado_cubicaje.xlsx', index=False)
 
    # Generar HTML con totales de pallets y tablas centradas
    html = ''
    for i, cont in enumerate(contenedores, 1):
        bc_name = cont['BC'].iloc[0]
        total_pallets = cont['Pallets asignados'].sum()
        table = cont.to_html(classes='table table-bordered table-striped text-center', index=False)
        table = table.replace('<thead>', '<thead class="text-center">')
 
        html += f'''
<div class="card mb-4 shadow-sm">
<div class="card-body">
<h3 class="card-title">Contenedor {i} - BC: {bc_name}</h3>
<p class="fw-bold">Total Pallets: {total_pallets}</p>
            {table}
</div>
</div>
        '''
 
    return f'''
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Resultado de Optimización</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
            rel="stylesheet">
<style>.table th,.table td{{text-align:center}}</style>
</head>
<body class="bg-light">
<div class="container py-5">
<h1 class="mb-4 text-center">Optimización Completada ✅</h1>
        {html}
<div class="text-center mt-4">
<a href="/download" class="btn btn-success btn-lg">📥 Descargar Excel</a>
<a href="/" class="btn btn-secondary btn-lg ms-3">Volver</a>
</div>
</div>
</body>
</html>
    '''
 
@app.route('/download')
def download_file():
    return send_file('resultado_cubicaje.xlsx', as_attachment=True)
 
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)


