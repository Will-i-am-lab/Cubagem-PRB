from flask import Flask, render_template, request, send_file
import pandas as pd
import os

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
    # renombrar si hace falta
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
    df = pd.read_pickle('temp.pkl')
    df['Pallets restantes'] = df['Pallets']
    # leer capacidades
    caps_by_bc = {
      bc: sorted([int(x) for x in request.form[bc].split(',') if x],reverse=True)
      for bc in df['BC'].unique()
    }

    conts = []
    cont_num = 1

    # 1) empaquetado normal
    for bc in df['BC'].unique():
        grupo = df[df['BC']==bc].copy()
        mayor, menor = caps_by_bc[bc][0], caps_by_bc[bc][-1]
        while grupo['Pallets restantes'].sum()>0:
            remtot = int(grupo['Pallets restantes'].sum())
            cap = mayor if remtot>=mayor else menor
            usados = 0
            sel=[]
            grupo = grupo.sort_values(['Lead time','Pallets restantes'],
                                      ascending=[True,False])
            for i,row in grupo.iterrows():
                if row['Pallets restantes']<=0: continue
                espacio=cap-usados
                if espacio<=0: break
                take=min(int(row['Pallets restantes']),espacio)
                sel.append({
                  'SKU':row['SKU'],
                  'Nombre SKU':row['Nombre SKU'],
                  'BC':bc,
                  'Pallets asignados':take,
                  'Cajas asignadas':take*row['Cajas por Pallet'],
                  'Lead time':row['Lead time'],
                  'Contenedor':cont_num
                })
                usados+=take
                grupo.at[i,'Pallets restantes'] -= take
                df.at[i,'Pallets restantes']    -= take
                if usados>=cap: break
            if not sel: break
            conts.append(pd.DataFrame(sel))
            cont_num+=1

    # 2) reempaque de los ULTIMOS DOS contenedores de CADA BC
    out=[]
    for bc in df['BC'].unique():
      grupo = [c for c in conts if c['BC'].iloc[0]==bc]
      mayor, menor = caps_by_bc[bc][0], caps_by_bc[bc][-1]
      if len(grupo)>=2:
        a,b = grupo[-2], grupo[-1]
        suma = int(a['Pallets asignados'].sum()+b['Pallets asignados'].sum())
        # si suma supera la pequeña, reempaquétalos en 2 conts de tamaño=menor
        if suma>menor:
          mini=pd.concat([a,b],ignore_index=True)
          mini['Pallets restantes']=mini['Pallets asignados']
          nuevos=[]
          # crear 2 contenedores pequeños
          for _ in range(2):
            usados=0
            sel2=[]
            mini=mini.sort_values(['Lead time','Pallets restantes'],
                                  ascending=[True,False])
            for i,row in mini.iterrows():
              if row['Pallets restantes']<=0: continue
              esp=menor-usados
              if esp<=0: break
              tk=min(int(row['Pallets restantes']),esp)
              sel2.append({
                'SKU':row['SKU'],
                'Nombre SKU':row['Nombre SKU'],
                'BC':bc,
                'Pallets asignados':tk,
                'Cajas asignadas':tk*row['Cajas por Pallet'],
                'Lead time':row['Lead time'],
                'Contenedor':None  # lo asignamos luego
              })
              usados+=tk
              mini.at[i,'Pallets restantes']-=tk
              if usados>=menor: break
            nuevos.append(pd.DataFrame(sel2))
          # sustituimos los dos últimos por estos 2 nuevos
          grupo = grupo[:-2] + nuevos
      # actualizamos contenedor IDs
      for dfc in grupo:
        dfc['Contenedor']=list(range(cont_num,cont_num+len(grupo)))
        cont_num+=1
      out+=grupo

    # 3) guardado y renderizado idéntico a antes
    res=pd.concat(out,ignore_index=True)
    res.to_excel('resultado_cubicaje.xlsx',index=False)

    html=''
    for idx, c in enumerate(out,1):
      total=c['Pallets asignados'].sum()
      th=c.to_html(classes='table table-bordered table-striped text-center',
                   index=False).replace('<thead>','<thead class="text-center">')
      bc=c['BC'].iloc[0]
      html+=f'''
      <div class="card mb-4 shadow-sm">
        <div class="card-body">
          <h3 class="card-title">Contenedor {idx} – BC: {bc}</h3>
          <p class="fw-bold">Total pallets: {total}</p>
          {th}
        </div>
      </div>'''

    return f'''
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="UTF-8"><title>Optimización ✅</title>
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

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)))


