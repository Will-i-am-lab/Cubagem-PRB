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
        df = pd.read_excel(file, engine='openpyxl')
        df['SKU'] = df['SKU'].astype(str).str.strip().str.upper()
        df['ETD'] = pd.to_datetime(df['ETD'])
        df['Paletes restantes'] = df['Paletes']
        df.to_pickle('temp_df.pkl')

        capacidad_por_sku = {
            '7126': [24, 21], '7128': [21], '7046': [24, 21], '7047': [21], '7141': [21],
            '7151': [21], '7147': [21], '7211': [20, 11], '7206': [20, 11], '7214': [24, 11],
            '7207': [24, 11], '7200': [15, 11], '7201': [15, 11], '7197': [15, 11], '7198': [15, 11],
            '7157': [15, 11], '7224': [20, 11], '7185': [15, 11], '7079': [20, 11], '7164': [24, 11],
            '7191': [17, 11], '7193': [17, 11], '7192': [13, 11], '7194': [13, 11], '7216': [15, 11],
            '7175': [15, 11], '7238': [20, 11], '7150': [15, 11], '7166': [20], '7169': [20],
            '7179': [20], '7232': [20], '8006': [11], '8009': [11], '8008': [11], '8027': [11],
            '8028': [11], '7203': [15, 11], '7088': [3]
        }

        pd.to_pickle(capacidad_por_sku, 'default_capacidades.pkl')
        return optimize()
    return 'Por favor suba um arquivo .xlsx válido ❌'

@app.route('/optimize', methods=['POST', 'GET'])
def optimize():
    df = pd.read_pickle('temp_df.pkl')
    capacidad_por_sku = pd.read_pickle('default_capacidades.pkl')

    df['SKU'] = df['SKU'].astype(str)
    df['Paletes restantes'] = df['Paletes']

    resultado = []
    cont_num = 1

    for (wh, bc), grupo in df.groupby(['WH', 'BC']):
        grupo = grupo.copy()
        while grupo['Paletes restantes'].sum() > 0:
            grupo = grupo[grupo['Paletes restantes'] > 0]
            if grupo.empty:
                break

            etd_base = grupo['ETD'].min()
            grupo_etd = grupo[grupo['ETD'].dt.month == etd_base.month]
            grupo_etd = grupo_etd.copy()
            grupo_etd['Capacidade SKU'] = grupo_etd['SKU'].map(lambda x: max(capacidad_por_sku.get(x, [11])))
            grupo_etd = grupo_etd.sort_values(['ETD', 'Capacidade SKU', 'Paletes restantes'], ascending=[True, False, False])

            cap = grupo_etd['Capacidade SKU'].iloc[0]
            paletes_atual = 0
            selecionados = []

            for idx, row in grupo_etd.iterrows():
                if row['Paletes restantes'] <= 0:
                    continue
                sku = row['SKU']
                allowed_caps = capacidad_por_sku.get(sku, [11])
                if cap not in allowed_caps:
                    continue
                espaco = cap - paletes_atual
                if espaco <= 0:
                    break
                take = min(row['Paletes restantes'], espaco)
                caixas = take * row['CA/Paletes']
                selecionados.append({
                    'SKU': sku,
                    'Descrição SKU': row['Descrição SKU'],
                    'WH': row['WH'],
                    'BC': row['BC'],
                    'Paletes atribuídos': take,
                    'Caixas atribuídas': caixas,
                    'ETD': row['ETD'],
                    'Contêiner': cont_num
                })
                paletes_atual += take
                grupo.loc[idx, 'Paletes restantes'] -= take
                df.loc[idx, 'Paletes restantes'] -= take
                if paletes_atual == cap:
                    break

            if selecionados:
                resultado.extend(selecionados)
                cont_num += 1
            else:
                break

    # Alocar paletes restantes em contêineres extras
    df_restantes = df[df['Paletes restantes'] > 0].copy()
    for idx, row in df_restantes.iterrows():
        pal_rest = row['Paletes restantes']
        if pal_rest <= 0:
            continue
        caixas = pal_rest * row['CA/Paletes']
        resultado.append({
            'SKU': row['SKU'],
            'Descrição SKU': row['Descrição SKU'],
            'WH': row['WH'],
            'BC': row['BC'],
            'Paletes atribuídos': pal_rest,
            'Caixas atribuídas': caixas,
            'ETD': row['ETD'],
            'Contêiner': cont_num
        })
        cont_num += 1

    resultado_df = pd.DataFrame(resultado)
    total_caixas = resultado_df['Caixas atribuídas'].sum()
    linha_total = pd.DataFrame([{
        'SKU': '',
        'Descrição SKU': '',
        'WH': '',
        'BC': '',
        'Paletes atribuídos': '',
        'Caixas atribuídas': total_caixas,
        'ETD': '',
        'Contêiner': 'TOTAL'
    }])
    resultado_df = pd.concat([resultado_df, linha_total], ignore_index=True)
    resultado_df.to_excel('resultado_cubicaje.xlsx', index=False)

    return send_file('resultado_cubicaje.xlsx', as_attachment=True)

@app.route('/download')
def download_file():
    return send_file('resultado_cubicaje.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
