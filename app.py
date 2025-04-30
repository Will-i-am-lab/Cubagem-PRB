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
            'CBL': [21, 15],
            'TAC': [21],
            'HCI': [22, 11],
            'PRM': [20],
            'IDL': [22, 10],
            'WYB': [21, 10],
        }

        return render_template('select_capacities.html',
                               bcs=bcs,
                               capacidad_default=capacidad_default)
    else:
        return 'Por favor sube un archivo .xlsx válido ❌'

@app.route('/optimize', methods=['POST'])
def optimize():
    df = pd.read_pickle('temp_df.pkl')
    df['Pallets restantes'] = df['Pallets']

    capacidad_por_bc = {}
    for bc in df['BC'].unique():
        capacidades = request.form.get(bc).split(',')
        capacidad_por_bc[bc] = [int(c.strip()) for c in capacidades if c.strip()]

    contenedores = []
    contenedor_num = 1

    for bc in df['BC'].unique():
        grupo_bc = df[df['BC'] == bc].copy()
        capacidades = sorted(capacidad_por_bc[bc], reverse=True)

        while grupo_bc['Pallets restantes'].sum() > 0:
            for capacidad_contenedor in capacidades:
                pallets_actuales = 0
                seleccionados = []
                skus_asignados = set()

                grupo_bc = grupo_bc.sort_values(
                    ['Lead time', 'Pallets restantes'],
                    ascending=[True, False]
                )
                if grupo_bc[grupo_bc['Pallets restantes'] > 0].empty:
                    break

                lead_time_objetivo = grupo_bc[
                    grupo_bc['Pallets restantes'] > 0
                ]['Lead time'].iloc[0]

                for idx, row in grupo_bc.iterrows():
                    pallets_disponibles = row['Pallets restantes']
                    if pallets_disponibles <= 0:
                        continue

                    sku_actual = row['SKU']
                    nombre_sku = row['Nombre SKU']
                    # límite de 5 SKUs por contenedor
                    if len(skus_asignados) >= 5 and sku_actual not in skus_asignados:
                        continue

                    if pallets_actuales >= capacidad_contenedor:
                        break

                    espacio_restante = capacidad_contenedor - pallets_actuales
                    pallets_asignados = min(pallets_disponibles, espacio_restante)
                    cajas_asignadas = pallets_asignados * row['Cajas por Pallet']

                    seleccionados.append({
                        'SKU': sku_actual,
                        'Nombre SKU': nombre_sku,
                        'BC': row['BC'],
                        'Pallets asignados': pallets_asignados,
                        'Cajas asignadas': cajas_asignadas,
                        'Lead time': row['Lead time'],
                        'Contenedor': contenedor_num
                    })

                    pallets_actuales += pallets_asignados
                    skus_asignados.add(sku_actual)
                    grupo_bc.at[idx, 'Pallets restantes'] -= pallets_asignados
                    df.at[idx, 'Pallets restantes'] -= pallets_asignados

                    if pallets_actuales >= capacidad_contenedor:
                        break

                if seleccionados:
                    contenedores.append(pd.DataFrame(seleccionados))
                    contenedor_num += 1
                    break
            else:
                break

    # Guardar resultado en Excel
    df_resultado = pd.concat(contenedores, ignore_index=True)
    df_resultado.to_excel('resultado_cubicaje.xlsx', index=False)

    # Construir el HTML de resultados
    html_resultado = ''
    for i, contenedor_df in enumerate(contenedores, start=1):
        bc_name = contenedor_df['BC'].iloc[0]
        total_pallets = contenedor_df['Pallets asignados'].sum()
        table_html = contenedor_df.to_html(
            classes='table table-bordered table-striped text-center',
            index=False
        )
        # Asegurar encabezados centrados
        table_html = table_html.replace('<thead>', '<thead class="text-center">')

        html_resultado += f'''
        <div class="card mb-4 shadow-sm">
          <div class="card-body">
            <h3 class="card-title">
              Contenedor {i} - BC: {bc_name}
            </h3>
            <p class="fw-bold">Total de Pallets en este contenedor: {total_pallets}</p>
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
      <style>
        .table th, .table td {{ text-align: center; }}
      </style>
    </head>
    <body class="bg-light">
      <div class="container py-5">
        <h1 class="mb-4 text-center">
          Optimización por BC y Capacidades Completada ✅
        </h1>
        {html_resultado}
        <div class="text-center mt-4">
          <a href="/download" class="btn btn-success btn-lg">
            📥 Descargar Resultado en Excel
          </a>
          <a href="/" class="btn btn-secondary btn-lg ms-3">
            Subir otro archivo
          </a>
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
    app.run(host='0.0.0.0', port=port)




