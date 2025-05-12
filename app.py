from flask import Flask, render_template, request, send_file
import pandas as pd, os, traceback

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    f = request.files['file']
    if not f.filename.endswith('.xlsx'):
        return '❌ Por favor sube un .xlsx'
    df = pd.read_excel(f)
    # Renombrar columna de cajas
    if 'Pallet Build per SKU' in df.columns:
        df.rename(columns={'Pallet Build per SKU':'Cajas por Pallet'}, inplace=True)
    df.to_pickle('temp.pkl')
    bcs = df['BC'].unique().tolist()
    defaults = {
      'CBL':[21,15], 'TAC':[21], 'HCI':[22,11],
      'PRM':[20], 'IDL':[22,10], 'WYB':[21,10]
    }
    return render_template('select_capacities.html',
                           bcs=bcs,
                           capacidad_default=defaults)

@app.route('/optimize', methods=['POST'])
def optimize():
    try:
        df = pd.read_pickle('temp.pkl')
        df['Pallets restantes'] = df['Pallets']

        # Leer capacidades
        caps_by_bc = {
          bc: sorted([int(x) for x in request.form[bc].split(',') if x.strip()],
                     reverse=True)
          for bc in df['BC'].unique()
        }

        # 1) Empaquetado normal
        conts = []
        cont_id = 1
        for bc in df['BC'].unique():
            mayor, menor = caps_by_bc[bc][0], caps_by_bc[bc][-1]
            grupo = df[df['BC']==bc].copy()
            while grupo['Pallets restantes'].sum() > 0:
                remtot = int(grupo['Pallets restantes'].sum())
                cap = mayor if remtot >= mayor else menor
                usados = 0
                sel = []
                grupo = grupo.sort_values(['Lead time','Pallets restantes'],
                                          ascending=[True,False])
                for i,row in grupo.iterrows():
                    r = int(row['Pallets restantes'])
                    if r<=0 or usados>=cap:
                        continue
                    take = min(r, cap-usados)
                    sel.append({
                      'SKU': row['SKU'],
                      'Nombre SKU': row['Nombre SKU'],
                      'BC': bc,
                      'Pallets asignados': take,
                      'Cajas asignadas': take * row['Cajas por Pallet'],
                      'Lead time': row['Lead time'],
                      'Contenedor': cont_id
                    })
                    usados += take
                    grupo.at[i,'Pallets restantes'] -= take
                    df.at[i,'Pallets restantes']   -= take
                if not sel:
                    break
                conts.append(pd.DataFrame(sel))
                cont_id += 1

        # 2) Reempaque últimos 2 contenedores por BC
        nuevos = []
        for bc in df['BC'].unique():
            # extraer sublista de contenedores de esta BC
            sub = [c for c in conts if c['BC'].iloc[0]==bc]
            mayor, menor = caps_by_bc[bc][0], caps_by_bc[bc][-1]
            if len(sub) >= 2:
                a, b = sub[-2], sub[-1]
                total = int(a['Pallets asignados'].sum() + b['Pallets asignados'].sum())
                if total > menor:
                    # aplanar registros
                    records = a.to_dict('records') + b.to_dict('records')
                    # crear dos nuevos DF pequeños
                    rec1, rec2 = [], []
                    acc = 0
                    for r in records:
                        qty = r['Pallets asignados']
                        # llenar primero contenedor de tamaño menor
                        if acc < menor:
                            take = min(qty, menor-acc)
                            rec = r.copy(); rec['Pallets asignados']=take
                            rec['Cajas asignadas']=take * r['Cajas por Pallet']
                            rec1.append(rec)
                            leftover = qty - take
                            if leftover>0:
                                r2 = r.copy(); r2['Pallets asignados']=leftover
                                r2['Cajas asignadas']=leftover * r['Cajas por Pallet']
                                rec2.append(r2)
                            acc += take
                        else:
                            rec2.append(r)
                    # reconstruir lista: todos menos los dos últimos + estos dos
                    prefix = [c for c in conts if c['BC'].iloc[0]!=bc] + sub[:-2]
                    # reasignar cont_id consecutivo
                    for dfnew in [pd.DataFrame(rec1), pd.DataFrame(rec2)]:
                        dfnew['Contenedor'] = cont_id
                        prefix.append(dfnew)
                        cont_id += 1
                    nuevos.extend(prefix)
                    continue
            # si no empaquetamos, los dejamos igual
            for c in sub:
                c['Contenedor'] = cont_id
                nuevos.append(c)
                cont_id += 1

        # 3) Guardar y renderizar
        final = pd.concat(nuevos, ignore_index=True)
        final.to_excel('resultado_cubicaje.xlsx', index=False)

        html = ''
        for idx, c in enumerate(nuevos, start=1):
            bc = c['BC'].iloc[0]
            tot = c['Pallets asignados'].sum()
            tbl = c.to_html(classes='table table-bordered table-striped text-center',
                             index=False).replace('<thead>', '<thead class="text-center">')
            html += f'''
            <div class="card mb-4 shadow-sm"><div class="card-body">
              <h3 class="card-title">Contenedor {idx} - BC: {bc}</h3>
              <p class="fw-bold">Total pallets: {tot}</p>
              {tbl}
            </div></div>'''

        return f'''
        <!DOCTYPE html><html lang="es"><head>
          <meta charset="UTF-8"><title>✅</title>
          <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
                rel="stylesheet">
          <style>.table th,.table td{{text-align:center}}</style>
        </head><body class="bg-light">
        <div class="container py-5">
          <h1 class="text-center mb-4">Optimización Completada ✅</h1>
          {html}
          <div class="text-center mt-4">
            <a href="/download" class="btn btn-success btn-lg">📥 Descargar Excel</a>
            <a href="/" class="btn btn-secondary btn-lg ms-3">Volver</a>
          </div>
        </div></body></html>
        '''
    except Exception:
        # imprime stacktrace en logs y muestra error genérico
        traceback.print_exc()
        return '❌ Error interno, revisa los logs.'

@app.route('/download')
def download_file():
    return send_file('resultado_cubicaje.xlsx', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)), debug=False)



