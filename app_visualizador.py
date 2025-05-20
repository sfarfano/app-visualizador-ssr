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

# --- UTILIDAD PARA EXPORTAR PENDIENTES ---
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
    pdf.output(output)
    return output

# --- CARGA DE DATOS Y AUTENTICACIÓN ---
st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/a/a3/Logo_CFC.svg/320px-Logo_CFC.svg.png", width=250)
st.title("🔍 Plataforma de Revisión de Documentos SSR")

try:
    autorizaciones = pd.read_excel("autorizaciones.xlsx")
    proyectos_nombres = pd.read_excel("estructura_189_proyectos.xlsx", sheet_name="Sheet1")
    df_checklist = pd.read_excel("CHECKLIST ETAPAS.xlsx", sheet_name="CHECKLIST ENTREGABLES")
    df_checklist = df_checklist[df_checklist.iloc[:, 2].notna()].rename(columns={
        df_checklist.columns[2]: "Entregable",
        df_checklist.columns[5]: "Equipo"
    })
    df_checklist["Entregable"] = df_checklist["Entregable"].astype(str).str.strip()
except Exception as e:
    st.error(f"Error al cargar archivos: {e}")
    st.stop()

diccionario_nombres = dict(zip(proyectos_nombres['Código'].astype(str).str.strip(), proyectos_nombres['Nombre Completo'].astype(str).str.strip()))

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = ""

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
        st.error("⚠️ El usuario no tiene SSR autorizados asignados en el archivo.")
        st.stop()

    proyectos_raw = ssr_autorizados.iloc[0]
    if not any(p.strip() for p in proyectos_raw.split(',')):
        st.error("⚠️ No hay SSR asignados válidos para este usuario.")
        st.stop()
    opciones_dict = {f"{p.strip()} - {diccionario_nombres.get(p.strip(), '')}": p.strip() for p in proyectos_raw.split(',') if p.strip()}
    opciones_ordenadas = dict(sorted(opciones_dict.items()))

    menu = st.sidebar.radio("Navegación", ["Visor", "Resumen SSR", "Explorador"])
    st.sidebar.markdown(f"**Usuario:** {usuario}")
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.autenticado = False
        st.session_state.usuario = ""
        st.rerun()

    if menu == "Resumen SSR":
        st.subheader("📊 Avance de Entregables por SSR")
        resumen_data = []
        for label, codigo in opciones_ordenadas.items():
            id_ssr = buscar_id_carpeta(codigo, FOLDER_BASE_ID)
            if not id_ssr:
                resumen_data.append((codigo, label, 0, 0, 0.0, []))
                continue
            archivos = listar_archivos(id_ssr)
            nombres_archivos = [a['name'].lower() for a in archivos]
            entregables_totales = 0
            entregables_cumplidos = 0
            entregables_pendientes = []
            for ent in df_checklist["Entregable"]:
                ent_normalizado = ent.lower()
                if "ptap" in ent_normalizado or "tratamiento" in ent_normalizado:
                    continue
                entregables_totales += 1
                if any(ent_normalizado in a for a in nombres_archivos):
                    entregables_cumplidos += 1
                else:
                    entregables_pendientes.append(ent)
            avance = round(entregables_cumplidos / entregables_totales * 100, 1) if entregables_totales else 0.0
            resumen_data.append((codigo, label, entregables_cumplidos, entregables_totales, avance, entregables_pendientes))

        for codigo, label, ok, total, avance, pendientes in resumen_data:
            st.markdown(f"### {codigo} - {label}")
            st.progress(min(int(avance), 100))
            st.write(f"{ok} de {total} entregables completos ({avance}%)")
            if pendientes:
                with st.expander("📌 Ver entregables pendientes"):
                    for item in pendientes:
                        st.markdown(f"- ❌ {item}")

        df_resumen = pd.DataFrame([
            (codigo, label, ok, total, avance) for codigo, label, ok, total, avance, _ in resumen_data
        ], columns=["Código SSR", "Nombre Proyecto", "Entregables OK", "Totales", "% Avance"])

        st.download_button(
    "📥 Descargar resumen en Excel",
    data=df_resumen.to_csv(index=False).encode("utf-8"),
    file_name="resumen_avance_ssr.csv",
    mime="text/csv"
)

# Botón para descargar pendientes por SSR
        pendientes_df = generar_csv_pendientes(resumen_data)
        if not pendientes_df.empty:
            st.download_button(
                "📌 Descargar entregables pendientes",
                data=pendientes_df.to_csv(index=False).encode("utf-8"),
                file_name="entregables_pendientes.csv",
                mime="text/csv"
            )

elif menu == "Visor":
        pass

elif menu == "Explorador":
        st.info("🔧 En desarrollo: explorador jerárquico con navegación entre subcarpetas y tipos de documentos.")
