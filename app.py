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
        skus = df['SKU'].unique().tolist()

        capacidad_por_sku = {
            'SKU001': [11],
            'SKU002': [21],
            'SKU003': [22, 11],
            'SKU004': [20],
            'SKU005': [22, 10],
            'SKU006': [21, 10],
        }

        return render_template('select_capacities.html',
                               bcs=skus,
                               capacidad_default=capacidad_por_sku)
    return 'Por favor suba um arquivo .xlsx válido ❌'

@app.route('/optimize', methods=['POST'])
def optimize():
    df = pd.read_pickle('temp_df.pkl')
    df['Pallets restantes'] = df['Pallets']

    capacidad_por_sku = {}
    for sku in df['SKU'].unique():
        cantidades = request.form.get(sku)
        if cantidades:
            capacidad_por_sku[sku] = [int(x) for x in cantidades.split(',') if x.strip()]
        else:
            capacidad_por_sku[sku] = [20]  # valor padrão se não informado

    contenedores = []
    cont_num = 1

    for wh in df['WH'].unique():
        grupo_wh = df[df['WH'] == wh]

        for bc in grupo_wh['BC'].unique():
            grupo_bc = grupo_wh[grupo_wh['BC'] == bc]

            for sku in grupo_bc['SKU'].unique():
                grupo_sku = grupo_bc[grupo_bc['SKU'] == sku].copy()

                while grupo_sku['Pallets restantes'].sum() > 0:
                    sum_rem = grupo_sku['Pallets restantes'].sum()
                    caps = capacidad_por_sku.get(sku, [20])

                    if sum_rem >= max(caps):
                        cap_sel = max(caps)
                    else:
                        cap_sel = min(caps, key=lambda c: abs(c - sum_rem))

                    pallets_actuales = 0
                    seleccion = []
                    skus_usados = set()

                    grupo_sku = grupo_sku.sort_values(['WH', 'BC', 'SKU', 'ETD', 'Pallets restantes'],
                                                      ascending=[True, True, True, True, False])

                    for idx, row in grupo_sku.iterrows():
                        if row['Pallets restantes'] <= 0:
                            continue

                        sku_actual = row['SKU']
                        nombre = row['Nombre SKU']

                        if len(skus_usados) >= 5 and pallets_actuales < cap_sel * 0.9:
                            pass
                        elif len(skus_usados) >= 5 and sku_actual not in skus_usados:
                            continue

                        espacio = cap_sel - pallets_actuales
                        if espacio <= 0:
                            break

                        take = min(row['Pallets restantes'], espacio)
                        cajas = take * row['Cajas por Pallet']

                        seleccion.append({
                            'SKU': sku_actual,
                            'Nombre SKU': nombre,
                            'WH': wh,
                            'BC': bc,
                            'Pallets asignados': take,
                            'Cajas asignadas': cajas,
                            'Lead time': row['Lead time'],
                            'ETD': row['ETD'],
                            'Contenedor': cont_num
                        })
                        pallets_actuales += take
                        skus_usados.add(sku_actual)

                        grupo_sku.at[idx, 'Pallets restantes'] -= take
                        df.at[idx, 'Pallets restantes'] -= take

                        if pallets_actuales >= cap_sel:
                            break

                    if seleccion:
                        contenedores.append(pd.DataFrame(seleccion))
                        cont_num += 1
                    else:
                        break

    resultado = pd.concat(contenedores, ignore_index=True)
    resultado.to_excel('resultado_cubicaje.xlsx', index=False)

    html = ''
    for i, cont in enumerate(contenedores, 1):
        wh_name = cont['WH'].iloc[0]
        total_pallets = cont['Pallets asignados'].sum()
        table = cont.to_html(classes='table table-bordered table-striped text-center', index=False)
        table = table.replace('<thead>', '<thead class="text-center">')

        html += f'''
<div class="card mb-4 shadow-sm">
<div class="card-body">
<h3 class="card-title">Contêiner {i} - WH: {wh_name}</h3>
<p class="fw-bold">Total de Pallets: {total_pallets}</p>
{table}
</div>
</div>
        '''

    return f'''
<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Resultado de Otimização</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.cssle th,.table td{{text-align:center}}</style>
</head>
<body class="bg-light">
<div class="container py-5">
<h1 class="mb-4 text-center">Otimização Concluída ✅</h1>
{html}
<div class="text-center mt-4">
<a href="/download" class="btn btn-success btn-lg">📥 Baixar Excel</a>
<a href="/" class="btn btn-secondary btn-lg ms-3">Voltar</a>
</div>
</div>
</body>
</html>
    '''

@app.route('/download')
def download_file():
    return send_file('resultado_cubicaje.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)


