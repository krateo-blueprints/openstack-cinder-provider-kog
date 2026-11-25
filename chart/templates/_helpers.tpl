{{/*
Expand the name of the chart.
*/}}
{{- define "openstack-cinder-provider-kog.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "openstack-cinder-provider-kog.fullname" -}}
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

{{/*
Chart label.
*/}}
{{- define "openstack-cinder-provider-kog.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "openstack-cinder-provider-kog.labels" -}}
helm.sh/chart: {{ include "openstack-cinder-provider-kog.chart" . }}
{{ include "openstack-cinder-provider-kog.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "openstack-cinder-provider-kog.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openstack-cinder-provider-kog.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Auth-bridge resource name.
*/}}
{{- define "openstack-cinder-provider-kog.authBridgeName" -}}
{{- printf "%s-auth-bridge" (include "openstack-cinder-provider-kog.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
In-cluster URL the generated controller calls instead of Cinder. It is the
OpenAPI document's servers[0].url. The auth-bridge listens here, adds a fresh
X-Auth-Token and forwards to the catalog's block-storage endpoint (or to
.Values.authBridge.upstreamEndpoint when set).
*/}}
{{- define "openstack-cinder-provider-kog.authBridgeUrl" -}}
http://{{ include "openstack-cinder-provider-kog.authBridgeName" . }}.{{ .Release.Namespace }}.svc.cluster.local:{{ .Values.authBridge.service.port }}
{{- end -}}
