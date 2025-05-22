import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from fpdf import FPDF
from io import BytesIO
from PIL import Image
import requests

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Visualizador Documentos SSR", layout="wide", page_icon="🔍")

# --- CONFIGURACIÓN GOOGLE DRIVE ---
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_BASE_ID = '1rByjj9IzT6nhUyvnZVJSUMprOWU0axKD'

@st.cache_resource
def conectar_drive():
    if 'GOOGLE_SERVICE_ACCOUNT_JSON' not in st.secrets:
        st.error("⚠️ No se encontró el secret 'GOOGLE_SERVICE_ACCOUNT_JSON'.")
        st.stop()
    service_info = json.loads(st.secrets['GOOGLE_SERVICE_ACCOUNT_JSON'])
    credentials = service_account.Credentials.from_service_account_info(service_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)

service = conectar_drive()

# --- FUNCIONES DE GOOGLE DRIVE ---

def generar_csv_pendientes(resumen):
    filas = []
    for codigo, label, _, _, _, pendientes in resumen:
        for item in pendientes:
            filas.append({
                "Código SSR": codigo,
                "Nombre Proyecto": label,
                "Entregable Pendiente": item
            })
    return pd.DataFrame(filas)

def buscar_id_carpeta(nombre, padre_id):
    query = f"name contains '{nombre}' and '{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resultados = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    archivos = resultados.get('files', [])
    return archivos[0]['id'] if archivos else None

def listar_archivos(carpeta_id):
    query = f"'{carpeta_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false"
    archivos = service.files().list(q=query, fields="files(id, name, webViewLink, modifiedTime, size, mimeType)" , supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    return archivos

def formato_peso(bytes_str):
    try:
        b = int(bytes_str)
        if b < 1024:
            return f"{b} B"
        elif b < 1024**2:
            return f"{b/1024:.1f} KB"
        elif b < 1024**3:
            return f"{b/1024**2:.1f} MB"
        else:
            return f"{b/1024**3:.1f} GB"
    except:
        return "-"

# --- CARGA DE DATOS Y AUTENTICACIÓN ---
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a3/Logo_CFC.svg/320px-Logo_CFC.svg.png", width=250)
st.title("🔍 Plataforma de Revisión de Documentos SSR")

try:
    autorizaciones = pd.read_excel("autorizaciones.xlsx")
    autorizaciones['Usuario'] = autorizaciones['Usuario'].astype(str).str.strip()
    autorizaciones['PIN'] = autorizaciones['PIN'].astype(str).str.strip()
    autorizaciones['SSR Autorizados'] = autorizaciones['SSR Autorizados'].astype(str).str.strip()
    autorizaciones['SSR Autorizados'] = autorizaciones['SSR Autorizados'].replace('nan', '')
    autorizaciones['SSR Autorizados'] = autorizaciones['SSR Autorizados'].apply(
        lambda x: ','.join([s.strip() for s in x.split(',') if s.strip()]) if isinstance(x, str) else ''
    )
except Exception as e:
    st.error(f"Error al cargar archivos: {e}")
    st.stop()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = ""

if st.button("Cerrar sesión"):
    st.session_state.autenticado = False
    st.session_state.usuario = ""
    st.rerun()

if not st.session_state.autenticado:
    with st.form("login_form"):
        usuario = st.text_input("Ingrese su usuario:")
        pin = st.text_input("Ingrese su PIN:", type="password")
        login = st.form_submit_button("Ingresar")
    if login:
        if not ((autorizaciones['Usuario'].astype(str).str.strip() == usuario.strip()) & (autorizaciones['PIN'].astype(str).str.strip() == pin.strip())).any():
            st.error("Usuario o PIN incorrecto.")
            st.stop()
        st.session_state.autenticado = True
        st.session_state.usuario = usuario.strip()
        st.rerun()

if st.session_state.autenticado:
    usuario = st.session_state.usuario
    usuario_data = autorizaciones[autorizaciones['Usuario'].astype(str).str.strip() == usuario]
    if usuario_data.empty:
        st.error("⚠️ Usuario no autorizado o sin proyectos asignados.")
        st.stop()

    ssr_autorizados = usuario_data['SSR Autorizados'].dropna()
    if ssr_autorizados.empty:
        st.error("⚠️ El usuario no tiene SSR autorizados asignados.")
        st.stop()

    try:
        proyectos_raw = ssr_autorizados.iloc[0] if not ssr_autorizados.empty else ""
    except IndexError:
        st.error("⚠️ No hay SSR asignados válidos para este usuario.")
        st.stop()

    if not isinstance(proyectos_raw, str) or not any(p.strip() for p in proyectos_raw.split(',')):
        st.error("⚠️ No hay SSR asignados válidos para este usuario.")
        st.stop()

    estructura = pd.read_excel("estructura_189_proyectos.xlsx")
    ssr_list = [s.strip() for s in proyectos_raw.split(",") if s.strip()]
    ssr_seleccionado = st.selectbox("Selecciona un proyecto SSR:", ssr_list)
    estructura_filtrada = estructura[estructura['Nombre del proyecto'].str.extract(r'(SSR\d{3})')[0] == ssr_seleccionado]
    st.subheader("📂 Estructura cargada")
    st.dataframe(estructura_filtrada, use_container_width=True)

    sub1_options = estructura_filtrada['Subcarpeta 1'].dropna().unique().tolist()
    subcarpeta1 = st.selectbox("Selecciona subcarpeta principal:", sub1_options)
    sub2_options = estructura_filtrada[estructura_filtrada['Subcarpeta 1'] == subcarpeta1]['Subcarpeta 2'].dropna().unique().tolist()
    subcarpeta2 = st.selectbox("Selecciona subcarpeta secundaria:", sub2_options) if sub2_options else None

    if st.button("🔍 Ver documentos"):
        with st.expander("🔎 Revisar documentos por proyecto", expanded=True):
            estructura_target = estructura_filtrada[
                (estructura_filtrada['Subcarpeta 1'] == subcarpeta1) &
                (estructura_filtrada['Subcarpeta 2'] == subcarpeta2 if subcarpeta2 else estructura_filtrada['Subcarpeta 2'].isna())
            ]
            for _, fila in estructura_target.iterrows():
                proyecto = fila['Nombre del proyecto']
                sub1 = fila['Subcarpeta 1']
                sub2 = fila['Subcarpeta 2'] if pd.notna(fila['Subcarpeta 2']) else None
                with st.container():
                    st.markdown(f"**📁 {proyecto} / {sub1}{' / ' + sub2 if sub2 else ''}**")
                    id_ssr = buscar_id_carpeta(proyecto.split(" - ")[0], FOLDER_BASE_ID)
                    if not id_ssr:
                        st.error("No se encontró carpeta SSR")
                        continue
                    id_sub1 = buscar_id_carpeta(sub1, id_ssr)
                    if not id_sub1:
                        st.warning("Subcarpeta 1 no encontrada")
                        continue
                    id_sub2 = buscar_id_carpeta(sub2, id_sub1) if sub2 else id_sub1
                    archivos = listar_archivos(id_sub2)
                    if not archivos:
                        st.info("No hay archivos disponibles.")
                    else:
                        for arch in archivos:
                            col1, col2 = st.columns([6,1])
                            with col1:
                                if 'image' in arch['mimeType']:
                                    try:
                                        img_data = requests.get(f"https://drive.google.com/uc?id={arch['id']}").content
                                        st.image(img_data, caption=arch['name'], use_column_width=True)
                                    except:
                                        st.warning(f"No se pudo mostrar la imagen: {arch['name']}")
                                elif 'pdf' in arch['mimeType']:
                                    st.markdown(f"**{arch['name']}**  _(modificado: {arch['modifiedTime'][:10]}, tamaño: {formato_peso(arch.get('size','0'))})_")
                                    st.components.v1.iframe(f"https://drive.google.com/file/d/{arch['id']}/preview", height=400)
                                else:
                                    st.markdown(f"- [{arch['name']}]({arch['webViewLink']})  _(modificado: {arch['modifiedTime'][:10]}, tamaño: {formato_peso(arch.get('size','0'))})_")
                            with col2:
                                st.download_button("⬇️", data=requests.get(arch['webViewLink']).content, file_name=arch['name'], mime=arch['mimeType'])

    if usuario == 'admin':
        st.divider()
        st.subheader("📝 Checklist de Etapas (solo visible para admin)")
        checklist_data = pd.read_excel("CHECKLIST ETAPAS.xlsx", header=None).dropna()
        checklist_items = checklist_data[0].tolist()
        checklist_matrix = pd.DataFrame(index=checklist_items, columns=ssr_list).fillna("Pendiente")
        st.dataframe(checklist_matrix, use_container_width=True)

    st.warning("⚠️ Modo seguro: funciones deshabilitadas hasta cargar estructura completa correctamente.")
