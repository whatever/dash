{{- define "dash.selectorLabels" -}}
{{- $root := index . 0 -}}
app: {{ index . 1 }}
{{ toYaml $root.Values.commonLabels }}
{{- end }}

{{- define "dash.labels" -}}
{{ include "dash.selectorLabels" . }}
helm.sh/chart: {{ printf "%s-%s" (index . 0).Chart.Name (index . 0).Chart.Version }}
{{- end }}

{{- define "dash.image" -}}
{{ .Values.dash.image.repository }}:{{ .Values.dash.image.tag | default .Chart.AppVersion }}
{{- end }}

{{- define "dash.url" -}}
{{ (index . 0).Values.scheme }}://{{ index . 1 }}
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
      secretKeyRef: { name: {{ include "dash.postgresSecret" . }}, key: DASH_DATABASE_URL }
  {{- if not .Values.redis.deploy }}
  - name: REDIS_URL
    valueFrom:
      secretKeyRef: { name: {{ .Values.redis.existingSecret }}, key: REDIS_URL }
  {{- end }}
  - name: HERMES_API_KEY
    valueFrom:
      secretKeyRef: { name: dash-hermes, key: API_SERVER_KEY }
  - name: NANGO_SECRET_KEY
    valueFrom:
      secretKeyRef: { name: dash, key: NANGO_SECRET_KEY, optional: true }
securityContext:
  allowPrivilegeEscalation: false
{{- end }}

{{- define "dash.postgresSecret" -}}
{{ ternary "dash-postgres" .Values.postgres.existingSecret .Values.postgres.deploy }}
{{- end }}

{{- define "dash.nangoUrl" -}}
{{ ternary "http://dash-nango:3003" .Values.nango.url .Values.nango.deploy }}
{{- end }}

{{- define "dash.nangoPublicUrl" -}}
{{ ternary (include "dash.url" (list . .Values.nango.host)) .Values.nango.url .Values.nango.deploy }}
{{- end }}

{{- define "dash.nangoConnectUrl" -}}
{{ ternary (include "dash.url" (list . .Values.nango.connectHost)) .Values.nango.connectUrl .Values.nango.deploy }}
{{- end }}

{{- define "dash.hermesUrl" -}}
{{ ternary "http://dash-agent:8642/v1" .Values.hermes.url .Values.hermes.deploy }}
{{- end }}
