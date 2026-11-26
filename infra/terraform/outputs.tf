output "api_key" {
  value     = random_password.api_key.result
  sensitive = true
}

output "grafana_password" {
  value     = random_password.grafana.result
  sensitive = true
}
