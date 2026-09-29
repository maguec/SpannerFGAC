# Spanner FGAC Sample

read a tfvars file file and build out a Spanner Fine Grained Access Control example

Build the terraform assuming that the Spanner Instance already exists

It should generate 4 user credentials in the local directory that have the following accesses

1. Full - Full access to the database
1. ReadWrite - Ability to read/write to the whole database
1. FullView - Ability to
1. Masked - Ability to only run a masked view of the data

The data should look like the following table with Faker generated 200 entries in a CSV file

id (uuidv4), first_name, last_name, ssn (masked), email, phone number(masked)
