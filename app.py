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

        df['SKU'] = df['SKU'].astype(str).str.strip().str.upper()
        df.to_pickle('temp_df.pkl')

        capacidad_por_sku = {
            '7126': [24, 21], '7128': [21], '7046': [24, 21], '7047': [21], '7141': [21],
            '7151': [21], '7147': [21], '7211': [20, 11], '7206': [20, 11], '7214': [24, 11],
            '7207': [24, 11], '7200': [15, 11], '7201': [15, 11], '7197': [15, 11], '7198': [15, 11],
            '7157': [15, 11], '7224': [20, 11], '7185': [15, 11], '7079': [20, 11], '7164': [24, 11],
            '7191': [17, 11], '7193': [17, 11], '7192': [13, 11], '7194': [13, 11], '7216': [15, 11],
            '7175': [15, 11], '7238': [20, 11], '7150': [15, 11], '7166': [20], '7169': [20],
            '7179': [20], '7232': [20], '8006': [11], '8009': [11], '8008': [11], '8027': [11],
            '8028': [11], '7203': [15,11]
        }

        pd.to_pickle(capacidad_por_sku, 'default_capacidades.pkl')

        return optimize()
    return 'Por favor suba um arquivo .xlsx válido ❌'

@app.route('/optimize', methods=['POST', 'GET'])
def optimize():
    df = pd.read_pickle('temp_df.pkl')
    df['Paletes restantes'] = df['Paletes']
    df['ETD'] = pd.to_datetime(df['ETD'])
    df['ETD_MES'] = df['ETD'].dt.to_period('M')
    capacidad_por_sku = pd.read_pickle('default_capacidades.pkl')

    contenedores = []
    cont_num = 1

    for wh in df['WH'].unique():
        grupo_wh = df[df['WH'] == wh]

        for bc in grupo_wh['BC'].unique():
            grupo_bc = grupo_wh[grupo_wh['BC'] == bc]

            while grupo_bc['Paletes restantes'].sum() > 0:
                grupo_bc = grupo_bc[grupo_bc['Paletes restantes'] > 0]
                if grupo_bc.empty:
                    break

                etd_base = grupo_bc.sort_values('ETD').iloc[0]['ETD']
                grupo_etd = grupo_bc[grupo_bc['ETD'] == etd_base]

                if grupo_etd['Paletes restantes'].sum() < 5:
                    grupo_etd = grupo_bc[grupo_bc['ETD_MES'] == etd_base.to_period('M')]

                paletes_atual = 0
                selecionados = []
                skus_usados = set()

                grupo_etd['Capacidade SKU'] = grupo_etd['SKU'].map(lambda x: max(capacidad_por_sku.get(x, [11])))
                grupo_etd = grupo_etd.sort_values(['ETD', 'Capacidade SKU', 'Paletes restantes'],
                                                  ascending=[True, False, False])

                caps = grupo_etd['Capacidade SKU'].unique()
                sum_rem = grupo_etd['Paletes restantes'].sum()
                cap_sel = max(caps) if sum_rem >= max(caps) else min(caps, key=lambda c: abs(c - sum_rem))

                for idx, row in grupo_etd.iterrows():
                    if row['Paletes restantes'] <= 0:
                        continue

                    sku_atual = row['SKU']
                    descricao = row['Descrição SKU']
                    espaco = cap_sel - paletes_atual
                    if espaco <= 0:
                        break

                    take = min(row['Paletes restantes'], espaco)
                    caixas = take * row['CA/Paletes']

                    selecionados.append({
                        'SKU': sku_atual,
                        'Descrição SKU': descricao,
                        'WH': wh,
                        'BC': bc,
                        'Paletes atribuídos': take,
                        'Caixas atribuídas': caixas,
                        'ETD': row['ETD'].strftime('%Y-%m-%d'),
                        'Contêiner': cont_num
                    })
                    paletes_atual += take
                    skus_usados.add(sku_atual)

                    grupo_etd.at[idx, 'Paletes restantes'] -= take
                    df.at[idx, 'Paletes restantes'] -= take

                    if paletes_atual >= cap_sel:
                        break

                if selecionados:
                    contenedores.append(pd.DataFrame(selecionados))
                    cont_num += 1
                else:
                    break

    resultado = pd.concat(contenedores, ignore_index=True)
    resultado.to_excel('resultado_cubicaje.xlsx', index=False)

    html = ''
    for i, cont in enumerate(contenedores, 1):
        wh_name = cont['WH'].iloc[0]
        total_paletes = cont['Paletes atribuídos'].sum()
        table = cont.to_html(classes='table table-bordered table-striped text-center', index=False)
        table = table.replace('<thead>', '<thead class="text-center">')

        html += f'''
<div class="card mb-4 shadow-sm">
<div class="card-body">
<h3 class="card-title">Contêiner {i} - WH: {wh_name}</h3>
<p class="fw-bold">Total de Paletes: {total_paletes}</p>
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
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheettext-align:center}}</style>
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

