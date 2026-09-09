{{- define "sberpi.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "sberpi.image" -}}
{{- $repository := required "image.repository is required" .repository -}}
{{- if .digest -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" .digest) -}}
{{- fail "image.digest must be sha256 followed by 64 lowercase hex characters; replace example placeholders" -}}
{{- end -}}
{{- printf "%s@%s" $repository .digest -}}
{{- else -}}
{{- printf "%s:%s" $repository (required "image.tag or image.digest is required" .tag) -}}
{{- end -}}
{{- end }}

{{- define "sberpi.secretFiles" -}}
{{- if not (has .Values.secrets.mode (list "files" "env")) -}}
{{- fail "secrets.mode must be files or env" -}}
{{- end -}}
{{- if eq .Values.secrets.mode "files" -}}true{{- end -}}
{{- end }}

{{- define "sberpi.dnsEgress" -}}
{{- with .Values.networkPolicy.dnsPeers }}
- to:
    {{- toYaml . | nindent 4 }}
  ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
{{- end }}
{{- end }}

{{- define "sberpi.databaseEgress" -}}
- to:
    {{- toYaml .Values.networkPolicy.database.peers | nindent 4 }}
  ports:
    - protocol: TCP
      port: {{ .Values.networkPolicy.database.port }}
{{- end }}

{{- define "sberpi.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "sberpi.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "sberpi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "sberpi.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sberpi.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "sberpi.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "sberpi.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
