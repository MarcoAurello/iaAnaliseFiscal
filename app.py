import streamlit as st
import requests

API_URL = "http://localhost:8000"  # Ajuste se backend estiver em outro lugar

st.title("Análise Tributária de Nota Fiscal")

# Seletor de tipo de envio
tipo_envio = st.radio("Como deseja enviar sua nota fiscal?", ( "Digitar Texto"))

# if tipo_envio == "Enviar PDF":
#     uploaded_file = st.file_uploader("Envie sua Nota Fiscal em PDF", type=["pdf"])
#     if uploaded_file:
#         with st.spinner("Enviando nota fiscal para análise..."):
#             files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
#             response = requests.post(f"{API_URL}/upload_nf/", files=files)
#             if response.status_code == 200:
#                 json_resp = response.json()
#                 if "error" in json_resp:
#                     st.error(json_resp["error"])
#                 else:
#                     st.success(json_resp["message"])
#                     st.markdown("### Resumo Tributário da Nota Fiscal:")
#                     st.write(json_resp.get("resumo_tributario", "Nenhum resumo disponível."))
#             else:
#                 st.error("Erro ao enviar arquivo para o backend.")

if tipo_envio == "Digitar Texto":
    texto_nf = st.text_area("Cole ou digite os dados da Nota Fiscal aqui:")
    if st.button("Enviar para Análise"):
        if texto_nf.strip() == "":
            st.warning("Digite o conteúdo da nota fiscal antes de enviar.")
        else:
            with st.spinner("Enviando texto para análise..."):
                response = requests.post(f"{API_URL}/upload_nf_texto/", json={"conteudo": texto_nf})
                if response.status_code == 200:
                    json_resp = response.json()
                    if "error" in json_resp:
                        st.error(json_resp["error"])
                    else:
                        st.success(json_resp["message"])
                        st.markdown("### Resumo Tributário da Nota Fiscal:")
                        st.write(json_resp.get("resumo_tributario", "Nenhum resumo disponível."))
                else:
                    st.error("Erro ao enviar texto para o backend.")
