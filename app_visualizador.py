import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from fpdf import FPDF
from io import BytesIO
from PIL import Image, UnidentifiedImageError
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

# --- FUNCIONES ---
def descargar_contenido_binario(file_id):
    request = service.files().get_media(fileId=file_id)
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read()

def buscar_id_carpeta(nombre, padre_id):
    query = f"name contains '{nombre}' and '{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    resultados = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    archivos = resultados.get('files', [])
    return archivos[0]['id'] if archivos else None

def listar_archivos(carpeta_id):
    query = f"'{carpeta_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed=false"
    archivos = service.files().list(q=query, fields="files(id, name, webViewLink, modifiedTime, size, mimeType)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    return archivos

def listar_todas_las_carpetas(padre_id):
    carpetas = []
    hijos = service.files().list(
        q=f"'{padre_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    for c in hijos:
        carpetas.append(c)
        carpetas += listar_todas_las_carpetas(c['id'])
    return carpetas

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

def generar_tabla_archivos(archivos):
    data = []
    for arch in archivos:
        data.append({
            'Archivo': arch['name'],
            'Tamaño (kB)': round(int(arch.get('size', 0)) / 1024, 1),
            'Última modificación': arch['modifiedTime'][:10],
            'Enlace': arch['webViewLink']
        })
    return pd.DataFrame(data)

def exportar_pdf(df, nombre_archivo):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=nombre_archivo, ln=True, align='C')
    pdf.ln(10)
    for index, row in df.iterrows():
        linea = f"{row['Archivo']} | {row['Tamaño (kB)']} kB | {row['Última modificación'] }"
        pdf.cell(200, 10, txt=linea, ln=True)
    output = BytesIO()
    pdf.output(name=output, dest='F')
    output.seek(0)
    return output

# --- CARGA DE DATOS Y AUTENTICACIÓN ---
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a3/Logo_CFC.svg/320px-Logo_CFC.svg.png", width=250)
st.title("🔍 Plataforma de Revisión de Documentos SSR")

try:
    autorizaciones = pd.read_excel("autorizaciones.xlsx")
except Exception as e:
    st.error(f"Error al cargar autorizaciones: {e}")
    st.stop()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = ""

if not st.session_state.autenticado:
    with st.form("login_form"):
        usuario = st.text_input("Ingrese su usuario:")
        pin = st.text_input("Ingrese su PIN:", type="password")
        login = st.form_submit_button("Ingresar")
    if login:
        autorizado = (
            (autorizaciones['Usuario'].astype(str).str.strip().str.lower() == usuario.strip().lower()) &
            (autorizaciones['PIN'].astype(str).str.strip() == pin.strip())
        ).any()
        if autorizado:
            st.session_state.autenticado = True
            st.session_state.usuario = usuario.strip().lower()
            st.rerun()
        else:
            st.error("Usuario o PIN incorrecto.")
    st.stop()

estructura = listar_todas_las_carpetas(FOLDER_BASE_ID)
estructura = sorted(estructura, key=lambda x: x['name'])
proyecto_seleccionado = st.selectbox("Selecciona un proyecto SSR:", [e['name'] for e in estructura])
carpeta_actual = next((e for e in estructura if e['name'] == proyecto_seleccionado), None)

# Resto del código continúa igual...


# Resto del código continúa igual...


# Módulo 5 - Checklist de etapas (visible solo para admin)
if st.session_state.get("usuario", "") == "admin":
    st.markdown("---")
    st.subheader("🗂️ Checklist de Etapas (solo visible para admin)")

    try:
        df_checklist = pd.read_excel("CHECKLIST ETAPAS.xlsx", sheet_name="CHECKLIST ENTREGABLES")
        df_checklist = df_checklist[df_checklist.iloc[:, 2].notna()].rename(columns={
            df_checklist.columns[2]: "Entregable",
            df_checklist.columns[5]: "Equipo"
        })
        df_checklist["Entregable"] = df_checklist["Entregable"].astype(str).str.strip()

        total = len(df_checklist)
        if "checklist_estado" not in st.session_state:
            st.session_state.checklist_estado = {proyecto_seleccionado: {item: False for item in df_checklist["Entregable"]}}

        st.write("### Nombre Proyecto")
        completados = 0
        for item in df_checklist["Entregable"]:
            estado = st.session_state.checklist_estado[proyecto_seleccionado].get(item, False)
            nuevo_estado = st.checkbox(item, value=estado, key=f"chk_{item}")
            st.session_state.checklist_estado[proyecto_seleccionado][item] = nuevo_estado
            if nuevo_estado:
                completados += 1

        avance = round((completados / total) * 100, 1) if total > 0 else 0.0
        st.success(f"✅ Avance: {completados} de {total} entregables completados ({avance}%)")

    except Exception as e:
        st.error(f"Error al cargar checklist de etapas: {e}")
