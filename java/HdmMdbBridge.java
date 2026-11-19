import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.util.*;

/** Ponte JDBC do aplicativo. Executa apenas SELECT SECTIONS e UPDATE parametrizado por PK. */
public class HdmMdbBridge {
    private static String quote(String identifier) {
        if (!identifier.matches("[A-Za-z_][A-Za-z_0-9]*")) {
            throw new IllegalArgumentException("Identificador SQL não permitido: " + identifier);
        }
        // UCanAccess aceita colchetes para nomes de tabelas/colunas do Access.
        // Aspas duplas podem ser tratadas como delimitadores de strings no dialeto Access.
        return "[" + identifier + "]";
    }
    private static String escaped(String text) {
        if (text == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (char ch : text.toCharArray()) {
            switch (ch) {
                case '\\': sb.append("\\\\"); break;
                case '"': sb.append("\\\""); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default: if (ch < 0x20) sb.append(String.format("\\u%04x", (int)ch)); else sb.append(ch);
            }
        }
        return sb.append('"').toString();
    }
    private static String scalar(Object item) {
        if (item == null) return "null";
        if (item instanceof Number || item instanceof Boolean) return item.toString();
        return escaped(item.toString());
    }
    private static String enc(String str) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(str.getBytes(StandardCharsets.UTF_8));
    }
    private static String dec(String str) {
        return new String(Base64.getUrlDecoder().decode(str), StandardCharsets.UTF_8);
    }
    private static String availableTables(Connection conn) {
        List<String> tableNames = new ArrayList<>();
        try (ResultSet catalog = conn.getMetaData().getTables(null, null, "%", new String[]{"TABLE"})) {
            while (catalog.next() && tableNames.size() < 80) {
                String name = catalog.getString("TABLE_NAME");
                if (name != null && !name.startsWith("MSys")) tableNames.add(name);
            }
            return tableNames.toString();
        } catch (SQLException ex) {
            return "(não foi possível obter metadados: " + ex.getMessage() + ")";
        }
    }
    private static void snapshot(Connection conn, String table, int maxRecords) throws SQLException {
        String sql = "SELECT * FROM " + quote(table);
        try (Statement stmt=conn.createStatement(); ResultSet rs=stmt.executeQuery(sql)) {
            ResultSetMetaData meta = rs.getMetaData();
            int n = meta.getColumnCount();
            StringBuilder sb=new StringBuilder();
            sb.append("{\"table\":").append(escaped(table)).append(",\"columns\":[");
            for (int i=1; i<=n; i++) {
                if (i>1) sb.append(',');
                sb.append(escaped(meta.getColumnLabel(i)));
            }
            sb.append("],\"rows\":[");
            int count=0;
            while (rs.next() && count < maxRecords) {
                if (count++>0) sb.append(',');
                sb.append('{');
                for (int i=1; i<=n; i++) {
                    if(i>1) sb.append(',');
                    sb.append(escaped(meta.getColumnLabel(i))).append(':');
                    Object val=rs.getObject(i);
                    sb.append(scalar(val));
                }
                sb.append('}');
            }
            sb.append("],\"shown_rows\":").append(count).append('}');
            System.out.println(sb.toString());
        } catch (SQLException ex) {
            throw new SQLException("Falha ao ler tabela " + table + " do MDB. "
                + "Tabelas disponíveis: " + availableTables(conn) + ". "
                + "Erro JDBC: " + ex.getMessage(), ex);
        }
    }
    private static void apply(Connection conn, String batchFile) throws Exception {
        List<String> lines=Files.readAllLines(Path.of(batchFile), StandardCharsets.UTF_8);
        int changed=0, skipped=0;
        conn.setAutoCommit(false);
        try {
            for (String line : lines) {
                if (line.isBlank()) continue;
                String[] bits=line.split("\\t", -1);
                if (bits.length != 6) throw new IllegalArgumentException("Registro de alteração inválido");
                String table=dec(bits[0]), keyColumn=dec(bits[1]), keyValue=dec(bits[2]), field=dec(bits[3]);
                double expected=Double.parseDouble(dec(bits[4])), requested=Double.parseDouble(dec(bits[5]));
                if (!Double.isFinite(expected) || !Double.isFinite(requested)) throw new IllegalArgumentException("Número inválido");
                String q="SELECT "+quote(field)+" FROM "+quote(table)+" WHERE "+quote(keyColumn)+" = ?";
                try (PreparedStatement stmt=conn.prepareStatement(q)) {
                    stmt.setString(1, keyValue);
                    try (ResultSet rs=stmt.executeQuery()) {
                        if (!rs.next()) throw new SQLException("Chave ausente em " + table+":"+keyValue);
                        double real=rs.getDouble(1);
                        if(rs.wasNull()) throw new SQLException("Campo de origem nulo em " + table+":"+field);
                        if(Math.abs(real-expected)>Math.max(1e-7,Math.abs(expected)*1e-8))
                            throw new SQLException("Conflito de concorrência em " + table + "." + field + " ("+expected+" != "+real+")");
                        if(rs.next()) throw new SQLException("Chave ambígua em " + table+":"+keyValue);
                    }
                }
                if (Math.abs(expected-requested)<=1e-9) { skipped++; continue; }
                String u="UPDATE "+quote(table)+" SET "+quote(field)+" = ? WHERE "+quote(keyColumn)+" = ?";
                try(PreparedStatement stmt=conn.prepareStatement(u)) {
                    stmt.setDouble(1, requested);
                    stmt.setString(2,keyValue);
                    int n=stmt.executeUpdate();
                    if(n!=1) throw new SQLException("Número inesperado de linhas alteradas: " + n);
                    changed++;
                }
            }
            conn.commit();
            System.out.println("{\"ok\":true,\"alterados\":"+changed+",\"sem_alteracao\":"+skipped+"}");
        } catch(Exception ex) {
            try {conn.rollback();} catch(Exception rollbackEx) {ex.addSuppressed(rollbackEx);}
            throw ex;
        }
    }
    public static void main(String[] args) throws Exception {
        if(args.length<3) throw new IllegalArgumentException("Uso: snapshot MDB TABLE ou apply MDB BATCHFILE");
        Class.forName("net.ucanaccess.jdbc.UcanaccessDriver");
        String command=args[0];
        Path path=Path.of(args[1]).toAbsolutePath().normalize();
        if(!Files.exists(path) || !path.getFileName().toString().toLowerCase().endsWith(".mdb"))
            throw new IllegalArgumentException("Arquivo MDB não encontrado");
        try(Connection conn=DriverManager.getConnection("jdbc:ucanaccess://" + path)) {
            if("snapshot".equals(command)) snapshot(conn,args[2],200);
            else if("apply".equals(command)) apply(conn,args[2]);
            else throw new IllegalArgumentException("Comando inválido");
        }
    }
}
