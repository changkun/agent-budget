// Runtime configuration. Values can be overridden with environment variables.
export const config = {
  port: Number(process.env.PORT) || 3000,
  host: process.env.HOST || '127.0.0.1',
  dataFile: process.env.BOOKSHELF_DATA || null,
  pageSizeDefault: 20,
  pageSizeMax: 100,
  titleMaxLength: 200,
  notesMaxLength: 5000,
  tagsMax: 10,
};
