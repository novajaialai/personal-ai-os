variable "hcloud_token" {
  type      = string
  sensitive = true
}

variable "tenant" {
  type = string # e.g. "jake" (tenant zero) or "acme"
}

variable "server_type" {
  type    = string
  default = "cpx41"
}

variable "location" {
  type    = string
  default = "ash" # ash=US east; fsn1=EU
}

variable "data_volume_gb" {
  type    = number
  default = 50
}

variable "ssh_key_ids" {
  type = list(string)
}

variable "admin_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"] # tighten to your IP in tfvars
}
