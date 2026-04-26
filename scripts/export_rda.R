#!/usr/bin/env Rscript
# Export an ICPSR .rda data frame to a gzip CSV.
# Usage: Rscript export_rda.R <input.rda> <output.csv.gz>
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: Rscript export_rda.R <input.rda> <output.csv.gz>")
}
input_path <- args[1]
output_path <- args[2]

env <- new.env()
load(input_path, envir = env)
obj_name <- ls(env)[1]
df <- get(obj_name, envir = env)

con <- gzfile(output_path, "w")
write.csv(df, con, row.names = FALSE)
close(con)
cat(sprintf("Wrote %d rows × %d cols from object '%s'\n", nrow(df), ncol(df), obj_name))
