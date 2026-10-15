{{- define "dash.selectorLabels" -}}
{{- $root := index . 0 -}}
app: {{ index . 1 }}
{{ toYaml $root.Values.global.commonLabels }}
{{- end }}

{{- define "dash.labels" -}}
{{ include "dash.selectorLabels" . }}
helm.sh/chart: {{ printf "%s-%s" (index . 0).Chart.Name (index . 0).Chart.Version }}
{{- end }}

{{- define "dash.image" -}}
{{ .Values.dash.image.repository }}:{{ .Values.dash.image.tag | default .Chart.AppVersion }}
{{- end }}

{{- define "dash.url" -}}
{{ (index . 0).Values.global.scheme }}://{{ index . 1 }}
{{- end }}

{{- define "dash.env" -}}
envFrom:
  - configMapRef:
      name: dash-env
  - secretRef:
      name: dash-bedrock
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef: { name: {{ .Values.global.configSecret }}, key: DASH_DATABASE_URL }
  - name: HERMES_API_KEY
    valueFrom:
      secretKeyRef: { name: dash-hermes, key: API_SERVER_KEY }
  - name: NANGO_SECRET_KEY
    valueFrom:
      secretKeyRef: { name: dash, key: NANGO_SECRET_KEY, optional: true }
securityContext:
  allowPrivilegeEscalation: false
{{- end }}
