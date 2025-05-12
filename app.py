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
    if not file.filename.endswith('.xlsx'):
        return 'Por favor sube un archivo .xlsx válido ❌'
    df = pd.read_excel(file)
    df.to_pickle('temp_df.pkl')
    bcs = df['BC'].unique().tolist()

    capacidad_default = {
        'CBL': [21, 15],
        'TAC': [21],
        'HCI': [22, 11],
        'PRM': [20],
        'IDL': [22, 10],
        'WYB': [21, 10],
    }

    return render_template(
        'select_capacities.html',
        bcs=bcs,
        capacidad_default=capacidad_default
    )

@app.route('/optimize', methods=['POST'])
def optimize():
    df = pd.read_pickle('temp_df.pkl')
    df['Pallets restantes'] = df['Pallets']

    # Leer capacidades por BC
    capacidad_por_bc = {}
    for bc in df['BC'].unique():
        caps = [int(x) for x in request.form[bc].split(',') if x.strip()]
        capacidad_por_bc[bc] = sorted(caps, reverse=True)

    contenedores = []
    cont_num = 1

    for bc in df['BC'].unique():
        grupo = df[df['BC'] == bc].copy()

        # Mientras queden pallets
        while grupo['Pallets restantes'].sum() > 0:
            sum_rem = int(grupo['Pallets restantes'].sum())
            caps = capacidad_por_bc[bc]
            mayor = caps[0]
            menor = caps[-1]

            # 1) Intentar llenar contenedor grande
            if sum_rem >= mayor:
                cap_sel = mayor
            else:
                # 2) Si no alcanza, usar el más pequeño
                cap_sel = menor

            pallets_actuales = 0
            seleccion = []
            skus = set()

            grupo = grupo.sort_values(
                ['Lead time', 'Pallets restantes'],
                ascending=[True, False]
            )

            for idx, row in grupo.iterrows():
                rem = int(row['Pallets restantes'])
                if rem <= 0:
                    continue

                sku = row['SKU']
                nombre = row['Nombre SKU']

                # Límite 5 SKUs si ya llenamos ≥90%
                if len(skus) >= 5 and pallets_actuales < cap_sel * 0.9:
                    pass
                elif len(skus) >= 5 and sku not in skus:
                    continue

                espacio = cap_sel - pallets_actuales
                if espacio <= 0:
                    break

                take = min(rem, espacio)
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
                grupo.at[idx, 'Pallets restantes'] -= take
                df.at[idx, 'Pallets restantes'] -= take

                if pallets_actuales >= cap_sel:
                    break

            # Si algo se asignó, guardamos
            if seleccion:
                contenedores.append(pd.DataFrame(seleccion))
                cont_num += 1
            else:
                break

    # Exportar a Excel
    resultado = pd.concat(contenedores, ignore_index=True)
    resultado.to_excel('resultado_cubicaje.xlsx', index=False)

    # Construir HTML de resultados
    html = ''
    for i, cont in enumerate(contenedores, start=1):
        bc_name = cont['BC'].iloc[0]
        total_pals = cont['Pallets asignados'].sum()
        table_html = cont.to_html(
            classes='table table-bordered table-striped text-center',
            index=False
        ).replace('<thead>', '<thead class="text-center">')

        html += f'''
        <div class="card mb-4 shadow-sm">
          <div class="card-body">
            <h3 class="card-title">Contenedor {i} - BC: {bc_name}</h3>
            <p class="fw-bold">Total de pallets: {total_pals}</p>
            {table_html}
          </div>
        </div>
        '''

    return f'''
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8">
      <title>Optimización Completada</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>.table th, .table td {{ text-align:center }}</style>
    </head>
    <body class="bg-light">
      <div class="container py-5">
        <h1 class="mb-4 text-center">Optimización por BC y Capacidades Completada ✅</h1>
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


