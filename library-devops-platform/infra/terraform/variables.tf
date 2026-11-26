variable "cluster_name" {
  type    = string
  default = "library"
}

variable "node_image" {
  description = "Pinned by digest. Works on cgroup v1 and v2 hosts."
  type        = string
  default     = "kindest/node:v1.34.3@sha256:08497ee19eace7b4b5348db5c6a1591d7752b164530a36f855cb0f2bdcbadd48"
}

variable "argo_rollouts_chart_version" {
  description = "Chart 2.43.7 ships Argo Rollouts 1.10.1, which fixes CVE-2026-82277."
  type        = string
  default     = "2.43.7"
}
